"""Pesquisa vinculada: referências públicas entram; observações confiáveis ficam no SQLite."""

import asyncio
import os
import re
import sqlite3
from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dona_maria.limits import call_fits
from dona_maria.persistence import SQLiteWorkspaceRepository, _decode_json
from dona_maria.planning import BusinessRuleError, canonical_json, fingerprint
from dona_maria.provenance import UUIDText, WebSource, source_fields
from dona_maria.research_network import ExtractionRecord, validate_url

ADAPTER_VERSION = "hermes-0.23.1-research-1"
TermID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    purpose: Literal["RECIPE", "QUOTE"]
    public_term_ids: Annotated[list[TermID], Field(min_length=1, max_length=200)]


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    research_result_id: UUIDText


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=4000)]


RESEARCH_TOOLS = {
    "search_culinary_sources": SearchRequest,
    "extract_culinary_source": ExtractRequest,
}


def migrate_research(repository: SQLiteWorkspaceRepository, backup: Path) -> None:
    """Migração explícita 2→3; nenhuma migração no startup do atendimento."""
    with repository.transaction() as db:
        repository.check_schema(db)
        versions = [
            r[0] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        if versions != [1, 2]:
            raise sqlite3.DatabaseError("Migração exige schema 2.")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Banco corrompido.")
        for row in db.execute("SELECT id FROM workspaces"):
            repository.load_state(db, row[0])
        descriptor = os.open(backup.resolve(), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with (
            closing(repository._connect("ro")) as source,
            closing(sqlite3.connect(backup)) as target,
        ):
            source.backup(target)
        db.execute(
            "CREATE TABLE research_observations ("
            "workspace_id TEXT NOT NULL REFERENCES workspaces(id), query_hash TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, receipt_hash TEXT NOT NULL, "
            "PRIMARY KEY(workspace_id, query_hash))"
        )
        db.execute("INSERT INTO schema_migrations VALUES (3, ?)", (datetime.now(UTC).isoformat(),))


def _require_research(db):
    SQLiteWorkspaceRepository.check_schema(db)
    if not db.execute("SELECT 1 FROM schema_migrations WHERE version=3").fetchone():
        raise BusinessRuleError("SOURCE_NOT_LINKED", "Pesquisa não habilitada neste contexto.")


def _document(row):
    document = _decode_json(row["payload_json"])
    if (
        not isinstance(document, dict)
        or document.get("version") != "1.0"
        or document.get("adapter_version") != ADAPTER_VERSION
        or fingerprint(document) != row["receipt_hash"]
        or document.get("workspace_id") != row["workspace_id"]
        or document.get("purpose") not in {"RECIPE", "QUOTE"}
        or any(
            not isinstance(document.get(field), str) or not document[field].strip()
            for field in ("query", "provider")
        )
        or fingerprint(
            [
                ADAPTER_VERSION,
                document["purpose"],
                document.get("query"),
                document.get("observation_id"),
            ]
        )
        != row["query_hash"]
    ):
        raise sqlite3.DatabaseError("Observação incompatível ou corrompida.")
    try:
        UUID(document["observation_id"])
        results = document["results"]
        if not isinstance(results, list) or len(results) > 5:
            raise ValueError
        for result in results:
            hit = SearchHit.model_validate(
                {
                    key: result["search_url"] if key == "url" else result[key]
                    for key in SearchHit.model_fields
                }
            )
            if fingerprint(hit.model_dump()) != result["search_sha256"]:
                raise ValueError
            fields = {
                "research_result_id",
                "url",
                "search_url",
                "title",
                "description",
                "observed_at",
                "status",
                "search_sha256",
            }
            if result["status"] == "COMPLETE":
                fields |= set(ExtractionRecord.model_fields) - {"text"}
                fields |= {"segments", "fetched_at", "text_sha256"}
            if set(result) != fields:
                raise ValueError
            UUID(result["research_result_id"])
            validate_url(result["url"])
            validate_url(result["search_url"])
            if datetime.fromisoformat(result["observed_at"]).tzinfo is None or (
                result["status"] not in {"SEARCHED", "COMPLETE"}
            ):
                raise ValueError
            if result["status"] == "COMPLETE":
                segments = result["segments"]
                keys = [f"segment-{i + 1}" for i in range(len(segments))]
                if set(segments) != set(keys) or any(
                    not 1 <= len(segments[k]) <= 4000 for k in keys
                ):
                    raise ValueError
                text = "".join(segments[key] for key in keys)
                if sha256(text.encode("utf-8")).hexdigest() != result["text_sha256"]:
                    raise ValueError
                ExtractionRecord.model_validate(
                    {
                        key: text if key == "text" else result[key]
                        for key in ExtractionRecord.model_fields
                    }
                )
                if datetime.fromisoformat(result["fetched_at"]).tzinfo is None:
                    raise ValueError
                if result["destinations"][0]["url"] != result["search_url"]:
                    raise ValueError
            elif result["url"] != result["search_url"]:
                raise ValueError
        return document
    except (ValueError, KeyError, TypeError, AttributeError, BusinessRuleError):
        raise sqlite3.DatabaseError("Observação inválida.") from None


def _find(db, workspace, identifier):
    _require_research(db)
    for row in db.execute("SELECT * FROM research_observations WHERE workspace_id=?", (workspace,)):
        document = _document(row)
        for result in document["results"]:
            if result["research_result_id"] == identifier:
                return row, document, result
    raise BusinessRuleError("SOURCE_NOT_LINKED", "Resultado não pertence ao contexto.")


def _search_view(document):
    return {key: document[key] for key in ("query", "purpose", "provider", "results")}


def materialize_web_source(db, workspace, identifier, segment, *, purpose):
    _, document, result = _find(db, workspace, str(identifier))
    if (
        result["status"] != "COMPLETE"
        or document["purpose"] != purpose
        or (segment not in result["segments"])
    ):
        raise BusinessRuleError("SOURCE_NOT_LINKED", "Fonte ou segmento não registrado.")
    return WebSource.model_validate(
        {
            "kind": "WEB",
            "url": result["url"],
            "title": result["title"],
            "excerpt": result["segments"][segment],
            "retrieved_at": result["fetched_at"],
            "research_result_id": str(identifier),
            "segment": segment,
            "content_sha256": result["content_sha256"],
        }
    ).model_dump(mode="json")


def verify_web_sources(db, workspace, value, *, purpose, legacy=frozenset()):
    """Igualdade com observação completa; leitura histórica não ganha confiança nova."""
    for _, source in source_fields(value):
        if source["kind"] != "WEB" or canonical_json(source) in legacy:
            continue
        expected = materialize_web_source(
            db, workspace, source.get("research_result_id"), source.get("segment"), purpose=purpose
        )
        if source != expected:
            raise BusinessRuleError("SOURCE_NOT_LINKED", "Fonte diverge da observação registrada.")


def resolve_web_references(repository, workspace, arguments):
    document = deepcopy(arguments)
    references = [
        s
        for _, s in source_fields(document)
        if s["kind"] == "WEB" and s.get("research_result_id") is not None
    ]
    if not references:
        return document
    purpose = "QUOTE" if document["command"]["kind"] == "register_complement_quote" else "RECIPE"
    with closing(repository._connect("ro")) as db:
        for source in references:
            expected = materialize_web_source(
                db, workspace, source["research_result_id"], source.get("segment"), purpose=purpose
            )
            if set(source) != {"kind", "research_result_id", "segment"} and source != expected:
                raise BusinessRuleError(
                    "SOURCE_NOT_LINKED", "Receipt não corresponde à observação."
                )
            source.clear()
            source.update(expected)
    return document


class ResearchService:
    def __init__(
        self, binding, approved_terms, *, search, extractor=None, clock=lambda: datetime.now(UTC)
    ):
        self.binding = binding
        self.repository = SQLiteWorkspaceRepository(binding.database)
        self.terms = dict(approved_terms)
        if (
            not self.terms
            or len(self.terms) > 200
            or any(
                not isinstance(key, str)
                or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", key)
                or not isinstance(term, str)
                or not 1 <= len(term) <= 100
                or any(not (c.isalpha() or c in " -") for c in term)
                or term != term.strip()
                for key, term in self.terms.items()
            )
        ):
            raise ValueError("Termos públicos inválidos; revise localmente.")
        self.search = search
        self.extractor = extractor
        self.clock = clock

    async def call(self, name, arguments):
        try:
            if name not in RESEARCH_TOOLS:
                raise BusinessRuleError("VALIDATION_ERROR", "Capacidade não disponível.")
            if not call_fits(arguments):
                raise BusinessRuleError("RESOURCE_LIMIT_EXCEEDED", "Pedido excede o limite.")
            request = RESEARCH_TOOLS[name].model_validate(arguments)
            async with asyncio.timeout(20):
                result = await (
                    self._search(request)
                    if name == "search_culinary_sources"
                    else self._extract(str(request.research_result_id))
                )
            return {"ok": True, "data": result}
        except BusinessRuleError as exc:
            code = (
                exc.code
                if exc.code
                in {
                    "SOURCE_NOT_LINKED",
                    "RESOURCE_LIMIT_EXCEEDED",
                    "SOURCE_INCOMPLETE",
                    "DESTINATION_REFUSED",
                    "COMPATIBILITY_BLOCKED",
                    "DATA_SOURCE_UNAVAILABLE",
                    "STALE_REVISION",
                    "CONTEXT_MISMATCH",
                    "VALIDATION_ERROR",
                }
                else "DATA_SOURCE_UNAVAILABLE"
            )
            return {
                "ok": False,
                "data": None,
                "error": {
                    "code": code,
                    "message": "Pesquisa recusada; revise as referências ou peça auxílio local.",
                },
            }
        except (ValidationError, ValueError, TypeError, RecursionError):
            return {
                "ok": False,
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Referências inválidas; revise o pedido.",
                },
            }
        except Exception:
            return {
                "ok": False,
                "data": None,
                "error": {
                    "code": "DATA_SOURCE_UNAVAILABLE",
                    "message": "Pesquisa indisponível; peça auxílio local.",
                },
            }

    async def _search(self, request):
        if any(key not in self.terms for key in request.public_term_ids):
            raise BusinessRuleError("SOURCE_NOT_LINKED", "Termo não liberado localmente.")
        terms = sorted(set(request.public_term_ids))
        query = (
            ("receita" if request.purpose == "RECIPE" else "oferta")
            + " "
            + " ".join(self.terms[key] for key in terms)
        )
        observation_id = str(uuid4())
        query_hash = fingerprint([ADAPTER_VERSION, request.purpose, query, observation_id])
        workspace = self.binding.workspace_id
        with closing(self.repository._connect("ro")) as db:
            _require_research(db)
            loaded = self.repository.load_state(db, workspace)
            if loaded is None:
                raise BusinessRuleError("CONTEXT_MISMATCH", "Contexto indisponível.")
            revision = loaded[0]
        hits = await self.search(query)
        if not isinstance(hits, list) or len(hits) > 5:
            raise BusinessRuleError("RESOURCE_LIMIT_EXCEEDED", "Resposta de busca excede o limite.")
        hits = [SearchHit.model_validate(hit).model_dump() for hit in hits]
        for hit in hits:
            validate_url(hit["url"])
        document = {
            "version": "1.0",
            "adapter_version": ADAPTER_VERSION,
            "observation_id": observation_id,
            "provider": getattr(self.search, "provider_name", "controlled-fixture"),
            "purpose": request.purpose,
            "workspace_id": workspace,
            "query": query,
            "results": [
                {
                    "research_result_id": str(uuid4()),
                    "url": hit["url"],
                    "search_url": hit["url"],
                    "title": hit["title"],
                    "description": hit["description"],
                    "observed_at": self.clock().isoformat(),
                    "status": "SEARCHED",
                    "search_sha256": fingerprint(hit),
                }
                for hit in hits
            ],
        }
        with self.repository.transaction() as db:
            _require_research(db)
            loaded = self.repository.load_state(db, workspace)
            if loaded is None or loaded[0] != revision:
                raise BusinessRuleError("STALE_REVISION", "Contexto alterado; repita a pesquisa.")
            db.execute(
                "INSERT INTO research_observations VALUES (?, ?, ?, ?)",
                (workspace, query_hash, canonical_json(document), fingerprint(document)),
            )
        return _search_view(document)

    def inspect_result(self, identifier):
        """Consulta local do registro para auditoria; não é uma ferramenta do modelo."""
        with closing(self.repository._connect("ro")) as db:
            return deepcopy(_find(db, self.binding.workspace_id, str(identifier))[2])

    def materialize_source(self, identifier, segment, *, purpose):
        with closing(self.repository._connect("ro")) as db:
            return materialize_web_source(
                db, self.binding.workspace_id, identifier, segment, purpose=purpose
            )

    async def _extract(self, identifier):
        workspace = self.binding.workspace_id
        with closing(self.repository._connect("ro")) as db:
            row, document, result = _find(db, workspace, identifier)
            loaded = self.repository.load_state(db, workspace)
            if loaded is None:
                raise BusinessRuleError("CONTEXT_MISMATCH", "Contexto indisponível.")
            revision = loaded[0]
            if result["status"] == "COMPLETE":
                return deepcopy(result)
            query_hash = row["query_hash"]
            original = deepcopy(result)
        if self.extractor is None:
            raise BusinessRuleError("DATA_SOURCE_UNAVAILABLE", "Extração não habilitada.")
        fetched = await self.extractor.extract(result["url"])
        try:
            fetched = ExtractionRecord.model_validate(fetched).model_dump(mode="json")
        except (ValidationError, ValueError, BusinessRuleError):
            raise BusinessRuleError(
                "SOURCE_INCOMPLETE", "Registro de extração incompleto."
            ) from None
        text = fetched["text"]
        if fetched["destinations"][0]["url"] != result["search_url"]:
            raise BusinessRuleError("SOURCE_NOT_LINKED", "Extração não corresponde ao resultado.")
        result.update(
            status="COMPLETE",
            url=fetched["url"],
            content_sha256=fetched["content_sha256"],
            text_sha256=sha256(text.encode("utf-8")).hexdigest(),
            fetched_at=self.clock().isoformat(),
            destinations=fetched["destinations"],
            complete=fetched["complete"],
            received_bytes=fetched["received_bytes"],
            decoded_bytes=fetched["decoded_bytes"],
            segments={
                f"segment-{i // 4000 + 1}": text[i : i + 4000] for i in range(0, len(text), 4000)
            },
        )
        with self.repository.transaction() as db:
            _, current, stored = _find(db, workspace, identifier)
            loaded = self.repository.load_state(db, workspace)
            if loaded is None or loaded[0] != revision:
                raise BusinessRuleError("STALE_REVISION", "Contexto alterado; repita a extração.")
            if stored["status"] == "COMPLETE":
                return deepcopy(stored)
            if stored != original:
                raise BusinessRuleError("SOURCE_NOT_LINKED", "Resultado alterado.")
            stored.update(result)
            db.execute(
                "UPDATE research_observations SET payload_json=?, receipt_hash=? "
                "WHERE workspace_id=? AND query_hash=?",
                (canonical_json(current), fingerprint(current), workspace, query_hash),
            )
        return deepcopy(result)
