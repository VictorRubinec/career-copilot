"""Coletor mensal da thread 'Ask HN: Who is hiring?' via API do Algolia."""

from __future__ import annotations

import re
from typing import Any

from ..config import get_logger
from ..models import RawJobOpportunity
from .base import clean_html, get_shared_http_client, is_location_eligible
from .http_client import ResilientHTTPClient

logger = get_logger(__name__)

HN_ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
DEFAULT_HN_KEYWORDS: tuple[str, ...] = ("remote", "async", "contractor", "python")

_SALARY_HINT_RE = re.compile(r"[\$€£]|\b\d{2,3}\s*k\b|\busd\b|\beur\b", re.IGNORECASE)
_LOCATION_HINT_RE = re.compile(
    r"\b(?:remote|worldwide|anywhere|latam|americas|brazil|brasil|us|usa|uk|eu|europe|utc|gmt|est|pst|cet|hybrid|onsite)\b",
    re.IGNORECASE,
)
_CONTRACT_HINT_RE = re.compile(
    r"\b(?:full[-\s]?time|part[-\s]?time|contract(?:or)?|freelance|b2b)\b",
    re.IGNORECASE,
)


def _find_latest_hiring_story_id(
    http: ResilientHTTPClient,
    use_cache: bool,
) -> str | None:
    payload = http.get_json(
        HN_ALGOLIA_SEARCH_URL,
        params={
            "query": '"Ask HN: Who is hiring"',
            "tags": "story,author_whoishiring",
            "hitsPerPage": "3",
        },
        use_cache=use_cache,
    )
    if not isinstance(payload, dict):
        return None

    hits = payload.get("hits", [])
    if not isinstance(hits, list):
        return None

    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "")
        if "who is hiring" in title.lower() and hit.get("objectID"):
            return str(hit["objectID"])
    return None


def _parse_hn_header(header_line: str) -> tuple[str, str, str, str, str]:
    """Extrai empresa, título, localização, tipo de contrato e salário do cabeçalho HN."""
    parts = [part.strip() for part in header_line.split("|") if part.strip()]
    if not parts:
        return ("HN Startup", "Software Engineer", "Remote", "Remote", "Não informado")

    empresa = parts[0][:100]
    titulo = parts[1][:120] if len(parts) >= 2 else "Software Engineer (HN Who is Hiring)"
    localizacao = "Remote"
    tipo_contrato = "Remote / Contractor"
    salario = "Não informado"

    extra_parts = parts[2:] if len(parts) > 2 else parts[1:]
    for fragment in extra_parts:
        if salario == "Não informado" and _SALARY_HINT_RE.search(fragment):
            salario = fragment[:80]
        if _CONTRACT_HINT_RE.search(fragment):
            tipo_contrato = fragment[:60]
        if _LOCATION_HINT_RE.search(fragment):
            localizacao = fragment[:100]

    return (empresa, titulo, localizacao, tipo_contrato, salario)


def mine_hackernews(
    keywords: tuple[str, ...] = DEFAULT_HN_KEYWORDS,
    max_hits_per_keyword: int = 40,
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas remotas elegíveis da thread mensal 'Who is Hiring' do Hacker News."""
    http = client or get_shared_http_client()
    story_id = _find_latest_hiring_story_id(http, use_cache=use_cache)
    if not story_id:
        logger.warning("Thread mensal 'Ask HN: Who is hiring' não encontrada na API Algolia.")
        return []

    seen_ids: set[str] = set()
    vagas: list[dict[str, Any]] = []

    for keyword in keywords:
        payload = http.get_json(
            HN_ALGOLIA_SEARCH_URL,
            params={
                "tags": f"comment,story_{story_id}",
                "query": keyword,
                "hitsPerPage": str(max_hits_per_keyword),
            },
            use_cache=use_cache,
        )
        if not isinstance(payload, dict):
            continue

        for hit in payload.get("hits", []):
            if not isinstance(hit, dict):
                continue
            obj_id = str(hit.get("objectID") or "").strip()
            if not obj_id or obj_id in seen_ids:
                continue
            if str(hit.get("parent_id") or "") != story_id:
                continue

            seen_ids.add(obj_id)
            raw_html = str(hit.get("comment_text") or "")
            texto_estruturado = clean_html(raw_html, preserve_newlines=True)
            if not texto_estruturado:
                continue

            linhas = [ln.strip() for ln in texto_estruturado.splitlines() if ln.strip()]
            header_line = linhas[0] if linhas else ""
            empresa, titulo, localizacao, tipo_contrato, salario = _parse_hn_header(header_line)
            desc = " ".join(texto_estruturado.split())

            if "remote" not in f"{localizacao} {desc}".lower():
                continue
            if not is_location_eligible(localizacao, desc):
                continue

            opportunity = RawJobOpportunity(
                id=f"hn_{obj_id}",
                fonte="HackerNews",
                origem="Internacional (USD/EUR)",
                empresa=empresa,
                titulo=titulo,
                localizacao=localizacao,
                tipo_contrato=tipo_contrato,
                salario=salario,
                url=f"https://news.ycombinator.com/item?id={obj_id}",
                data_publicacao=str(hit.get("created_at") or "")[:10],
                descricao=desc,
                resumo=desc[:240] + "..." if len(desc) > 240 else desc,
            )
            vagas.append(opportunity.model_dump())

    return vagas
