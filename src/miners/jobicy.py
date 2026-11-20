"""Coletor da API pública do Jobicy."""

from __future__ import annotations

import json
from typing import Any

from ..config import get_logger
from ..models import RawJobOpportunity
from .base import (
    clean_html,
    fetch_raw_url,
    format_salary_range,
    is_location_eligible,
    normalize_contract_type,
)
from .http_client import ResilientHTTPClient

logger = get_logger(__name__)


def mine_jobicy(
    count: int = 35,
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas remotas elegíveis da API pública do Jobicy."""
    vagas: list[dict[str, Any]] = []
    url = f"https://jobicy.com/api/v2/remote-jobs?count={count}&industry=engineering"
    raw = fetch_raw_url(url, use_cache=use_cache, client=client)
    if not raw:
        return vagas

    try:
        data = json.loads(raw.decode("utf-8"))
        for job in data.get("jobs", []):
            local = str(job.get("jobGeo") or "Anywhere")
            desc = clean_html(job.get("jobDescription", ""))
            if not is_location_eligible(local, desc):
                continue

            salario = format_salary_range(
                job.get("annualSalaryMin"),
                job.get("annualSalaryMax"),
                str(job.get("salaryCurrency") or ""),
            )

            opportunity = RawJobOpportunity(
                id=f"jobicy_{job.get('id')}",
                fonte="Jobicy",
                origem="Internacional (USD/EUR)",
                empresa=str(job.get("companyName") or ""),
                titulo=str(job.get("jobTitle") or ""),
                localizacao=local,
                tipo_contrato=normalize_contract_type(job.get("jobType")),
                salario=salario,
                url=str(job.get("url") or ""),
                data_publicacao=str(job.get("pubDate") or "")[:10],
                descricao=desc,
                resumo=desc[:240] + "..." if len(desc) > 240 else desc,
            )
            vagas.append(opportunity.model_dump())
    except Exception as exc:
        logger.warning("Erro ao processar resposta do Jobicy: %s", exc)

    return vagas
