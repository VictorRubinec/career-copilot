"""Coletor de repositórios brasileiros de vagas remotas no GitHub."""

from __future__ import annotations

import json
import os
from typing import Any

from ..config import get_logger
from ..models import RawJobOpportunity
from .base import clean_html, fetch_raw_url
from .http_client import ResilientHTTPClient

logger = get_logger(__name__)

GITHUB_BR_REPOS: tuple[str, ...] = ("backend-br/vagas", "qa-brasil/vagas")


def mine_github_brasil(
    limit: int = 30,
    client: ResilientHTTPClient | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Coleta vagas nacionais abertas em repositórios da comunidade no GitHub."""
    vagas: list[dict[str, Any]] = []
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for repo in GITHUB_BR_REPOS:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page={limit}"
        raw = fetch_raw_url(url, use_cache=use_cache, headers=headers, client=client)
        if not raw:
            continue

        try:
            issues = json.loads(raw.decode("utf-8"))
            if not isinstance(issues, list):
                continue

            for issue in issues:
                if not isinstance(issue, dict) or "pull_request" in issue:
                    continue

                titulo = str(issue.get("title") or "")
                corpo = clean_html(issue.get("body", ""))
                labels = [str(l.get("name") or "") for l in issue.get("labels", []) if isinstance(l, dict)]
                texto_total = f"{titulo} {corpo} {' '.join(labels)}".lower()

                if "remoto" not in texto_total and "remote" not in texto_total:
                    continue

                opportunity = RawJobOpportunity(
                    id=f"gh_{issue.get('id')}",
                    fonte=f"GitHub BR ({repo})",
                    origem="Nacional (BRL / PJ)",
                    empresa="Comunidade / Empresa Anunciante",
                    titulo=titulo,
                    localizacao="Brasil (100% Remoto)",
                    tipo_contrato="PJ / Remoto Flexível",
                    salario="A combinar / PJ",
                    url=str(issue.get("html_url") or ""),
                    data_publicacao=str(issue.get("created_at") or "")[:10],
                    descricao=corpo,
                    resumo=corpo[:240] + "..." if len(corpo) > 240 else corpo,
                )
                vagas.append(opportunity.model_dump())
        except Exception as exc:
            logger.warning("Erro ao processar issues de %s: %s", repo, exc)

    return vagas
