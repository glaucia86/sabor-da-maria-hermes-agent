"""Busca ao vivo no perfil selecionado, sem gravar observações ou estado de negócio."""

import asyncio
import json


async def check(settings):
    from pathlib import Path

    from tools.url_safety import create_ssrf_safe_async_client

    from dona_maria.business_state import AttendanceService
    from dona_maria.hermes_research import HermesSearchAdapter
    from dona_maria.research import ResearchService, SearchHit
    from dona_maria.research_network import SecureExtractor

    binding = AttendanceService(Path(settings["database"]), settings["workspace_id"], "ATTENDANCE")
    adapter = HermesSearchAdapter(settings["search_provider"])
    research = ResearchService(binding, settings["public_terms"], search=adapter)
    query = "receita " + research.terms[sorted(research.terms)[0]]
    async with asyncio.timeout(45):
        hits = await adapter(query)
        hit = SearchHit.model_validate(hits[0])
        record = await SecureExtractor(client_factory=create_ssrf_safe_async_client).extract(
            hit.url
        )
    return {
        "research": "LIVE_SEARCH_AND_EXTRACTION_PASS",
        "provider": adapter.provider_name,
        "authentication": "ANONYMOUS" if adapter.provider_name == "exa" else "PROVIDER_CONFIG",
        "query": query,
        "url": record["url"],
        "title": hit.title,
        "content_sha256": record["content_sha256"],
        "extracted_characters": len(record["text"]),
        "business_writes": False,
        "desktop_conversation": "NOT_TESTED",
    }


def main():
    try:
        from hermes_cli.config import load_config_readonly

        settings = load_config_readonly()["plugins"]["entries"]["dona-maria-mediated-research"][
            "settings"
        ]
        from dona_maria.hermes_research import _load_application

        _load_application(settings["application_source"])
        report = asyncio.run(check(settings))
    except Exception:
        print(json.dumps({"research": "UNAVAILABLE", "business_writes": False}))
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
