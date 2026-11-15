"""Política estrita de destinos do S17; sem execução de conteúdo externo."""

import asyncio
import hashlib
import ipaddress
import socket
import zlib
from html.parser import HTMLParser
from typing import Annotated, Literal
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from dona_maria.planning import BusinessRuleError

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024


def _limit():
    raise BusinessRuleError("RESOURCE_LIMIT_EXCEEDED", "Conteúdo excede o limite permitido.")


def public_ip(address):
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise BusinessRuleError("DESTINATION_REFUSED", "Destino de rede não permitido.")
    return str(ip)


def validate_url(url):
    try:
        if (
            not isinstance(url, str)
            or not 1 <= len(url) <= 2048
            or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in url)
        ):
            raise ValueError
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.port not in (None, 443)
            or "@" in parsed.netloc
            or "%" in parsed.netloc
            or parsed.fragment
            or parsed.hostname.rstrip(".").lower() in {"metadata.google.internal", "metadata.goog"}
        ):
            raise ValueError
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            pass
        else:
            public_ip(parsed.hostname)
        return parsed
    except (ValueError, TypeError):
        raise BusinessRuleError("DESTINATION_REFUSED", "Destino de rede não permitido.") from None


class ConnectionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    hostname: str
    address: str
    port: Literal[443]
    url: str

    @model_validator(mode="after")
    def public_destination(self):
        parsed = validate_url(self.url)
        if self.hostname.lower().rstrip(".") != parsed.hostname.encode(
            "idna"
        ).decode().lower().rstrip("."):
            raise ValueError("Hostname diverge do destino.")
        public_ip(self.address)
        return self


class ExtractionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: str
    text: str
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    complete: StrictBool
    received_bytes: Annotated[StrictInt, Field(ge=1, le=MAX_RESPONSE_BYTES)]
    decoded_bytes: Annotated[StrictInt, Field(ge=1, le=MAX_RESPONSE_BYTES)]
    destinations: Annotated[list[ConnectionObservation], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def complete_public_content(self):
        validate_url(self.url)
        if (
            not self.complete
            or not self.text.strip()
            or len(self.text.encode("utf-8")) > MAX_TEXT_BYTES
        ):
            raise ValueError("Extração incompleta ou excessiva.")
        if self.destinations[-1].url != self.url:
            raise ValueError("URL final diverge da conexão.")
        return self


class _PinnedBackend:
    def __init__(self, backend, resolver, connections):
        self.backend, self.resolver, self.connections = backend, resolver, connections

    async def connect_tcp(self, host, port, **kwargs):
        answers = await asyncio.to_thread(self.resolver, host, port, type=socket.SOCK_STREAM)
        addresses = [answer[4][0] for answer in answers]
        if not addresses:
            raise BusinessRuleError("DESTINATION_REFUSED", "Destino sem endereço público.")
        for address in addresses:
            public_ip(address)
        # O hostname original continua no httpcore para Host/TLS/SNI; somente TCP usa IP.
        ip = addresses[0]
        stream = await self.backend.connect_tcp(ip, port, **kwargs)
        try:
            peer = stream.get_extra_info("server_addr")
            if not peer or public_ip(peer[0]) != public_ip(ip):
                raise BusinessRuleError(
                    "DESTINATION_REFUSED", "Conexão diverge do destino validado."
                )
        except BaseException:
            await stream.aclose()
            raise
        self.connections.append({"hostname": host, "address": ip, "port": port})
        return stream

    async def connect_unix_socket(self, *args, **kwargs):
        raise BusinessRuleError("DESTINATION_REFUSED", "Transporte não permitido.")

    async def sleep(self, seconds):
        await self.backend.sleep(seconds)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "template", "noscript", "object"}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "template", "noscript", "object"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


class SecureExtractor:
    """Reutiliza o cliente SSRF do host, com política mais estrita por conexão."""

    def __init__(self, *, client_factory, resolver=socket.getaddrinfo):
        self.client_factory, self.resolver = client_factory, resolver

    async def extract(self, url):
        connections = []
        async with asyncio.timeout(20):
            for redirects in range(4):
                validate_url(url)
                status, headers, body, received = await self._fetch(url, connections)
                if status in {301, 302, 303, 307, 308}:
                    if redirects == 3 or not headers.get("location"):
                        raise BusinessRuleError(
                            "DESTINATION_REFUSED", "Limite de redirecionamentos."
                        )
                    url = urljoin(url, headers["location"])
                    continue
                try:
                    decoded = body.decode("utf-8")
                except UnicodeError:
                    raise BusinessRuleError(
                        "SOURCE_INCOMPLETE", "Codificação da fonte não suportada."
                    ) from None
                if headers.get("content-type", "").split(";")[0].strip().lower() == "text/plain":
                    text = " ".join(decoded.split())
                else:
                    parser = _Text()
                    parser.feed(decoded)
                    text = " ".join(" ".join(parser.parts).split())
                if not text:
                    raise BusinessRuleError("SOURCE_INCOMPLETE", "Fonte sem texto extraído.")
                if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
                    _limit()
                return {
                    "url": url,
                    "text": text,
                    "content_sha256": hashlib.sha256(body).hexdigest(),
                    "destinations": connections,
                    "complete": True,
                    "received_bytes": received,
                    "decoded_bytes": len(body),
                }

    async def _fetch(self, url, connections):
        async with self.client_factory(
            trust_env=False,
            follow_redirects=False,
            timeout=20,
            verify=True,
            cookies={},
            auth=None,
            headers={"Accept": "text/html, text/plain", "Accept-Encoding": "gzip, deflate"},
        ) as client:
            try:
                backend = client._transport._pool._network_backend
                if client._mounts:
                    raise ValueError
            except (AttributeError, ValueError):
                raise BusinessRuleError(
                    "COMPATIBILITY_BLOCKED", "Transporte do host incompatível."
                ) from None
            client._transport._pool._network_backend = _PinnedBackend(
                backend, self.resolver, connections
            )
            async with client.stream("GET", url) as response:
                for connection in connections:
                    connection.setdefault("url", url)
                body = b""
                received = 0
                if response.status_code not in {301, 302, 303, 307, 308}:
                    if response.status_code != 200 or "content-range" in response.headers:
                        raise BusinessRuleError(
                            "SOURCE_INCOMPLETE", "Fonte incompleta ou indisponível."
                        )
                    if response.headers.get("content-type", "").split(";")[
                        0
                    ].strip().lower() not in {"text/html", "text/plain", "application/xhtml+xml"}:
                        raise BusinessRuleError(
                            "SOURCE_INCOMPLETE", "Formato de fonte não suportado."
                        )
                    encoding = response.headers.get("content-encoding", "identity").lower()
                    if encoding not in {"identity", "gzip", "deflate"}:
                        raise BusinessRuleError("SOURCE_INCOMPLETE", "Compressão não suportada.")
                    decoder = (
                        zlib.decompressobj(31 if encoding == "gzip" else 15)
                        if (encoding != "identity")
                        else None
                    )
                    async for chunk in response.aiter_raw():
                        received += len(chunk)
                        if received > MAX_RESPONSE_BYTES:
                            _limit()
                        decoded = (
                            decoder.decompress(chunk, MAX_RESPONSE_BYTES - len(body) + 1)
                            if (decoder is not None)
                            else chunk
                        )
                        body += decoded
                        if len(body) > MAX_RESPONSE_BYTES:
                            _limit()
                    if decoder is not None and (not decoder.eof or decoder.unused_data):
                        raise BusinessRuleError(
                            "SOURCE_INCOMPLETE", "Conteúdo comprimido incompleto."
                        )
                return response.status_code, response.headers, body, received
