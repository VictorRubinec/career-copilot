"""Coletor RSS do We Work Remotely."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from ..config import get_logger
from ..models import RawJobOpportunity
from .base import (
    clean_html,
    fetch_raw_url,
    is_location_eligible,
    make_deterministic_id,
)
from .http_client import ResilientHTTPClient

logger = get_logger(__name__)

WWR_FEEDS: tuple[str, ...] = (
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
)


def mine_weworkremotely(
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas do RSS do We Work Remotely (Backend e DevOps)."""
    vagas: list[dict[str, Any]] = []

    for feed_url in WWR_FEEDS:
        raw = fetch_raw_url(feed_url, use_cache=use_cache, client=client)
        if not raw:
            continue

        try:
            root = ET.fromstring(raw)
            channel = root.find("channel")
            if channel is None:
                continue

            for item in channel.findall("item"):
                titulo_completo = item.findtext("title", "") or ""
                link = (item.findtext("link", "") or "").strip()
                pub_date = (item.findtext("pubDate", "") or "")[:16]
                desc = clean_html(item.findtext("description", ""))
                regiao = (item.findtext("region", "") or "Worldwide / Remote").strip()

                if not is_location_eligible(regiao, desc):
                    continue

                partes = titulo_completo.split(":", 1)
                if len(partes) == 2:
                    empresa = partes[0].strip()
                    titulo = partes[1].strip()
                else:
                    empresa = "Empresa Remota"
                    titulo = titulo_completo.strip()

                opportunity = RawJobOpportunity(
                    id=make_deterministic_id("wwr", link or titulo_completo),
                    fonte="WeWorkRemotely",
                    origem="Internacional (USD)",
                    empresa=empresa,
                    titulo=titulo,
                    localizacao=regiao,
                    tipo_contrato="Contractor / Full Remote",
                    salario="Não informado no feed",
                    url=link,
                    data_publicacao=pub_date,
                    descricao=desc,
                    resumo=desc[:240] + "..." if len(desc) > 240 else desc,
                )
                vagas.append(opportunity.model_dump())
        except Exception as exc:
            logger.warning("Erro ao processar RSS WeWorkRemotely (%s): %s", feed_url, exc)

    return vagas
