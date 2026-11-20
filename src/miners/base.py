import urllib.request
import re
from ..config import USER_AGENT


def fetch_raw_url(url, timeout=12):
    """Realiza requisição HTTP GET retornando bytes ou None em caso de falha."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/xml, */*"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except Exception:
        return None


def clean_html(text):
    """Remove tags HTML simples de descrições."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    return " ".join(clean.split())
