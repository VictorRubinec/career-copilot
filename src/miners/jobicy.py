import json
from .base import fetch_raw_url, clean_html


def mine_jobicy(count=35):
    """Coleta vagas da API pública do Jobicy."""
    vagas = []
    url = f"https://jobicy.com/api/v2/remote-jobs?count={count}&industry=engineering"
    raw = fetch_raw_url(url)
    if not raw:
        return vagas

    try:
        data = json.loads(raw)
        for job in data.get("jobs", []):
            local = job.get("jobGeo", "Anywhere")
            local_lower = local.lower()
            if any(r in local_lower for r in ["uk only", "us only"]):
                continue

            desc = clean_html(job.get("jobDescription", ""))
            salario = f"{job.get('annualSalaryMin', '')}-{job.get('annualSalaryMax', '')} {job.get('salaryCurrency', '')}".strip()
            if salario == "-":
                salario = "Não informado"

            vagas.append({
                "id": f"jobicy_{job.get('id')}",
                "fonte": "Jobicy",
                "origem": "Internacional (USD/EUR)",
                "empresa": job.get("companyName", ""),
                "titulo": job.get("jobTitle", ""),
                "localizacao": local,
                "tipo_contrato": str(job.get("jobType", "Remote")),
                "salario": salario,
                "url": job.get("url", ""),
                "data_publicacao": job.get("pubDate", "")[:10],
                "descricao": desc,
                "resumo": desc[:240] + "..." if len(desc) > 240 else desc
            })
    except Exception:
        pass

    return vagas
