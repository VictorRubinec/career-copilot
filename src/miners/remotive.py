import json
from .base import fetch_raw_url, clean_html


def mine_remotive(limit=40):
    """Coleta vagas da API pública do Remotive."""
    vagas = []
    url = f"https://remotive.com/api/remote-jobs?category=software-dev&limit={limit}"
    raw = fetch_raw_url(url)
    if not raw:
        return vagas

    try:
        data = json.loads(raw)
        for job in data.get("jobs", []):
            local = job.get("candidate_required_location", "Worldwide")
            local_lower = local.lower()
            if any(r in local_lower for r in ["uk only", "us only", "canada only", "germany only"]):
                continue

            desc = clean_html(job.get("description", ""))
            vagas.append({
                "id": f"remotive_{job.get('id')}",
                "fonte": "Remotive",
                "origem": "Internacional (USD)",
                "empresa": job.get("company_name", ""),
                "titulo": job.get("title", ""),
                "localizacao": local,
                "tipo_contrato": job.get("job_type", "Full-time"),
                "salario": job.get("salary", "Não informado"),
                "url": job.get("url", ""),
                "data_publicacao": job.get("publication_date", "")[:10],
                "descricao": desc,
                "resumo": desc[:240] + "..." if len(desc) > 240 else desc
            })
    except Exception:
        pass

    return vagas
