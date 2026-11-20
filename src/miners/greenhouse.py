"""Coletor da API pública de job boards do Greenhouse."""

from __future__ import annotations

from typing import Any

from ..config import get_logger, load_ats_boards
from ..models import RawJobOpportunity
from .base import (
    clean_html,
    get_shared_http_client,
    is_location_eligible,
    normalize_contract_type,
)
from .http_client import ResilientHTTPClient

logger = get_logger(__name__)

GREENHOUSE_API_TEMPLATE = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"


def _extract_contract_type(metadata: Any) -> str:
    if isinstance(metadata, list):
        for item in metadata:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").lower()
            if "employment" in name or "type" in name or "contract" in name:
                val = item.get("value")
                if val:
                    return normalize_contract_type(val)
    return "Remote"


def mine_greenhouse(
    companies: list[str] | None = None,
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas remotas elegíveis da API pública do Greenhouse."""
    board_slugs = (
        companies
        if companies is not None
        else load_ats_boards().get("greenhouse", [])
    )
    if not board_slugs:
        return []

    http = client or get_shared_http_client()
    vagas: list[dict[str, Any]] = []

    for slug in board_slugs:
        url = GREENHOUSE_API_TEMPLATE.format(company=slug)
        data = http.get_json(url, params={"content": "true"}, use_cache=use_cache)
        if not isinstance(data, dict):
            continue

        for job in data.get("jobs", []):
            if not isinstance(job, dict):
                continue
            loc_obj = job.get("location")
            local = (
                str(loc_obj.get("name") or "")
                if isinstance(loc_obj, dict)
                else str(loc_obj or "")
            ).strip() or "Remote"

            desc = clean_html(job.get("content", ""))
            titulo = str(job.get("title") or "").strip()
            loc_lower = local.lower()
            desc_lower = desc.lower()

            is_remote_role = any(
                k in loc_lower for k in ("remote", "remoto", "anywhere", "worldwide", "global")
            ) or any(
                k in desc_lower
                for k in ("fully remote", "100% remote", "remote-first", "work from anywhere")
            )
            if not is_remote_role or not is_location_eligible(local, desc):
                continue

            empresa = str(job.get("company_name") or slug.replace("-", " ").title())
            data_pub = str(job.get("updated_at") or job.get("first_published") or "")[:10]
            tipo_contrato = _extract_contract_type(job.get("metadata"))

            opportunity = RawJobOpportunity(
                id=f"ghb_{slug}_{job.get('id')}",
                fonte=f"Greenhouse ({slug})",
                origem="Internacional (USD/EUR)",
                empresa=empresa,
                titulo=titulo,
                localizacao=local,
                tipo_contrato=tipo_contrato,
                salario="Não informado",
                url=str(job.get("absolute_url") or ""),
                data_publicacao=data_pub,
                descricao=desc,
                resumo=desc[:240] + "..." if len(desc) > 240 else desc,
            )
            vagas.append(opportunity.model_dump())

    return vagas
