import xml.etree.ElementTree as ET
from .base import fetch_raw_url, clean_html


def mine_weworkremotely():
    """Coleta vagas do RSS do We Work Remotely (Backend e DevOps)."""
    vagas = []
    feeds = [
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"
    ]

    for feed_url in feeds:
        raw = fetch_raw_url(feed_url)
        if not raw:
            continue
        try:
            root = ET.fromstring(raw)
            channel = root.find("channel")
            if channel is None:
                continue

            for item in channel.findall("item"):
                titulo_completo = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")[:16]
                desc = clean_html(item.findtext("description", ""))

                partes = titulo_completo.split(":", 1)
                if len(partes) == 2:
                    empresa = partes[0].strip()
                    titulo = partes[1].strip()
                else:
                    empresa = "Empresa Remota"
                    titulo = titulo_completo

                vagas.append({
                    "id": f"wwr_{abs(hash(link)) % 1000000}",
                    "fonte": "WeWorkRemotely",
                    "origem": "Internacional (USD)",
                    "empresa": empresa,
                    "titulo": titulo,
                    "localizacao": "Worldwide / Remote",
                    "tipo_contrato": "Contractor / Full Remote",
                    "salario": "Não informado no feed",
                    "url": link,
                    "data_publicacao": pub_date,
                    "descricao": desc,
                    "resumo": desc[:240] + "..." if len(desc) > 240 else desc
                })
        except Exception:
            pass

    return vagas
