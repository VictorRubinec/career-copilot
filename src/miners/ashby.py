"""Coletor da API pública de job boards do Ashby."""

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

ASHBY_API_TEMPLATE = "https://api.ashbyhq.com/posting-api/job-board/{company}"


def _format_ashby_compensation(comp: Any) -> str:
    if isinstance(comp, dict):
        summary = comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary")
        if summary:
            return str(summary).strip()
    return "Não informado"


def _collect_ashby_locations(job: dict[str, Any]) -> str:
    parts: list[str] = []
    primary = str(job.get("location") or "").strip()
    if primary:
        parts.append(primary)
    secondary = job.get("secondaryLocations")
    if isinstance(secondary, list):
        for item in secondary:
            if isinstance(item, dict):
                loc_val = str(item.get("location") or "").strip()
                if loc_val and loc_val not in parts:
                    parts.append(loc_val)
    return ", ".join(parts) if parts else "Remote"


def mine_ashby(
    companies: list[str] | None = None,
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas remotas elegíveis da API pública do Ashby."""
    board_slugs = (
        companies
        if companies is not None
        else load_ats_boards().get("ashby", [])
    )
    if not board_slugs:
        return []

    http = client or get_shared_http_client()
    vagas: list[dict[str, Any]] = []

    for slug in board_slugs:
        url = ASHBY_API_TEMPLATE.format(company=slug)
        data = http.get_json(
            url,
            params={"includeCompensation": "true"},
            use_cache=use_cache,
        )
        if not isinstance(data, dict):
            continue

        empresa = slug.replace("-", " ").title()
        for job in data.get("jobs", []):
            if not isinstance(job, dict) or job.get("isListed") is False:
                continue

            workplace = str(job.get("workplaceType") or "").strip().lower()
            is_remote_flag = bool(job.get("isRemote"))
            if workplace in {"onsite", "on-site", "hybrid"} and not is_remote_flag:
                continue

            local = _collect_ashby_locations(job)
            desc_plain = str(job.get("descriptionPlain") or "").strip()
            desc = (
                " ".join(desc_plain.split())
                if desc_plain
                else clean_html(job.get("descriptionHtml", ""))
            )

            is_remote_role = (
                is_remote_flag
                or workplace == "remote"
                or any(
                    k in local.lower()
                    for k in ("remote", "remoto", "anywhere", "worldwide", "global")
                )
            )
            if not is_remote_role or not is_location_eligible(local, desc):
                continue

            opportunity = RawJobOpportunity(
                id=f"ashby_{slug}_{job.get('id')}",
                fonte=f"Ashby ({slug})",
                origem="Internacional (USD/EUR)",
                empresa=empresa,
                titulo=str(job.get("title") or "").strip(),
                localizacao=local,
                tipo_contrato=normalize_contract_type(job.get("employmentType") or "Remote"),
                salario=_format_ashby_compensation(job.get("compensation")),
                url=str(job.get("jobUrl") or job.get("applyUrl") or ""),
                data_publicacao=str(job.get("publishedAt") or "")[:10],
                descricao=desc,
                resumo=desc[:240] + "..." if len(desc) > 240 else desc,
            )
            vagas.append(opportunity.model_dump())

    return vagas
