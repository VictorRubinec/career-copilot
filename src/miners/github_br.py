import json
from .base import fetch_raw_url, clean_html


def mine_github_brasil(limit=30):
    """Coleta vagas nacionais e latino-americanas abertas em repositórios da comunidade."""
    vagas = []
    repos = ["backend-br/vagas", "qa-brasil/vagas"]

    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page={limit}"
        raw = fetch_raw_url(url)
        if not raw:
            continue

        try:
            issues = json.loads(raw)
            for issue in issues:
                if "pull_request" in issue:
                    continue

                titulo = issue.get("title", "")
                corpo = clean_html(issue.get("body", ""))
                labels = [l.get("name", "") for l in issue.get("labels", [])]
                texto_total = f"{titulo} {corpo} {' '.join(labels)}".lower()

                if "remoto" not in texto_total and "remote" not in texto_total:
                    continue

                vagas.append({
                    "id": f"gh_{issue.get('id')}",
                    "fonte": f"GitHub BR ({repo})",
                    "origem": "Nacional (BRL / PJ)",
                    "empresa": "Comunidade / Empresa Anunciante",
                    "titulo": titulo,
                    "localizacao": "Brasil (100% Remoto)",
                    "tipo_contrato": "PJ / Remoto Flexível",
                    "salario": "A combinar / PJ",
                    "url": issue.get("html_url", ""),
                    "data_publicacao": issue.get("created_at", "")[:10],
                    "descricao": corpo,
                    "resumo": corpo[:240] + "..." if len(corpo) > 240 else corpo
                })
        except Exception:
            pass

    return vagas
