"""Coletor da API pública do Remotive."""

from __future__ import annotations

import json
from typing import Any

from ..config import get_logger
from ..models import RawJobOpportunity
from .base import (
    clean_html,
    fetch_raw_url,
    is_location_eligible,
    normalize_contract_type,
)
from .http_client import ResilientHTTPClient

logger = get_logger(__name__)


def mine_remotive(
    limit: int = 40,
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas remotas elegíveis da API pública do Remotive."""
    vagas: list[dict[str, Any]] = []
    url = f"https://remotive.com/api/remote-jobs?category=software-dev&limit={limit}"
    raw = fetch_raw_url(url, use_cache=use_cache, client=client)
    if not raw:
        return vagas

    try:
        data = json.loads(raw.decode("utf-8"))
        for job in data.get("jobs", []):
            local = str(job.get("candidate_required_location") or "Worldwide")
            desc = clean_html(job.get("description", ""))
            if not is_location_eligible(local, desc):
                continue

            opportunity = RawJobOpportunity(
                id=f"remotive_{job.get('id')}",
                fonte="Remotive",
                origem="Internacional (USD)",
                empresa=str(job.get("company_name") or ""),
                titulo=str(job.get("title") or ""),
                localizacao=local,
                tipo_contrato=normalize_contract_type(job.get("job_type", "Full-time")),
                salario=str(job.get("salary") or "Não informado"),
                url=str(job.get("url") or ""),
                data_publicacao=str(job.get("publication_date") or "")[:10],
                descricao=desc,
                resumo=desc[:240] + "..." if len(desc) > 240 else desc,
            )
            vagas.append(opportunity.model_dump())
    except Exception as exc:
        logger.warning("Erro ao processar resposta do Remotive: %s", exc)

    return vagas
