"""Coletor da API pública de job boards do Lever."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import get_logger, load_ats_boards
from ..models import RawJobOpportunity
from .base import (
    clean_html,
    format_salary_range,
    get_shared_http_client,
    is_location_eligible,
    normalize_contract_type,
)
from .http_client import ResilientHTTPClient

logger = get_logger(__name__)

LEVER_API_TEMPLATE = "https://api.lever.co/v0/postings/{company}"


def _epoch_ms_to_date(epoch_ms: Any) -> str:
    if isinstance(epoch_ms, (int, float)) and epoch_ms > 0:
        try:
            dt = datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return ""
    return ""


def _build_lever_description(job: dict[str, Any]) -> str:
    sections: list[str] = []
    desc_plain = str(job.get("descriptionPlain") or "").strip()
    if desc_plain:
        sections.append(desc_plain)
    elif job.get("description"):
        sections.append(clean_html(str(job.get("description"))))

    lists_data = job.get("lists")
    if isinstance(lists_data, list):
        for item in lists_data:
            if not isinstance(item, dict):
                continue
            heading = str(item.get("text") or "").strip()
            content = clean_html(str(item.get("content") or ""))
            if heading or content:
                sections.append(f"{heading}: {content}".strip(": "))

    additional_plain = str(job.get("additionalPlain") or "").strip()
    if additional_plain:
        sections.append(additional_plain)
    elif job.get("additional"):
        sections.append(clean_html(str(job.get("additional"))))

    return " ".join(" ".join(sections).split())


def mine_lever(
    companies: list[str] | None = None,
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas remotas elegíveis da API pública do Lever."""
    board_slugs = (
        companies
        if companies is not None
        else load_ats_boards().get("lever", [])
    )
    if not board_slugs:
        return []

    http = client or get_shared_http_client()
    vagas: list[dict[str, Any]] = []

    for slug in board_slugs:
        url = LEVER_API_TEMPLATE.format(company=slug)
        data = http.get_json(url, params={"mode": "json"}, use_cache=use_cache)
        if not isinstance(data, list):
            continue

        empresa = slug.replace("-", " ").title()
        for job in data:
            if not isinstance(job, dict):
                continue

            workplace = str(job.get("workplaceType") or "").strip().lower()
            if workplace in {"onsite", "on-site", "hybrid"}:
                continue

            categories = job.get("categories") if isinstance(job.get("categories"), dict) else {}
            all_locs = categories.get("allLocations")
            if isinstance(all_locs, list) and all_locs:
                local = ", ".join(str(x).strip() for x in all_locs if str(x).strip())
            else:
                local = str(categories.get("location") or job.get("country") or "Remote").strip()

            desc = _build_lever_description(job)
            is_remote_role = workplace == "remote" or any(
                k in local.lower()
                for k in ("remote", "remoto", "anywhere", "worldwide", "global")
            )
            if not is_remote_role or not is_location_eligible(local, desc):
                continue

            salary_obj = job.get("salaryRange")
            if isinstance(salary_obj, dict):
                salario = format_salary_range(
                    salary_obj.get("min"),
                    salary_obj.get("max"),
                    str(salary_obj.get("currency") or ""),
                )
            else:
                salario = "Não informado"

            job_id = str(job.get("id") or "")
            job_url = str(
                job.get("hostedUrl")
                or job.get("applyUrl")
                or f"https://jobs.lever.co/{slug}/{job_id}"
            )

            opportunity = RawJobOpportunity(
                id=f"lever_{slug}_{job_id}",
                fonte=f"Lever ({slug})",
                origem="Internacional (USD/EUR)",
                empresa=empresa,
                titulo=str(job.get("text") or "").strip(),
                localizacao=local,
                tipo_contrato=normalize_contract_type(categories.get("commitment") or "Remote"),
                salario=salario,
                url=job_url,
                data_publicacao=_epoch_ms_to_date(job.get("createdAt")),
                descricao=desc,
                resumo=desc[:240] + "..." if len(desc) > 240 else desc,
            )
            vagas.append(opportunity.model_dump())

    return vagas
