"""Utilitários compartilhados entre os coletores (limpeza HTML, IDs e elegibilidade geográfica)."""

from __future__ import annotations

import ast
import hashlib
import html
import re
from typing import Any

from .http_client import ResilientHTTPClient

_default_client: ResilientHTTPClient | None = None

_ELIGIBLE_LOCATION_RE = re.compile(
    r"\b(?:worldwide|anywhere|global|latam|latin\s+america|south\s+america|"
    r"americas|brazil|brasil)\b",
    re.IGNORECASE,
)

_ANYWHERE_SCOPED_RE = re.compile(
    r"\banywhere\s+in\s+(?:the\s+)?(?:us|usa|u\.s\.|united\s+states|uk|u\.k\.|"
    r"united\s+kingdom|canada|europe|eu|australia|india|germany|north\s+america)\b",
    re.IGNORECASE,
)

_BLOCKED_LOCATION_RE = re.compile(
    r"\b(?:us|usa|u\.s\.|u\.s\.a\.|united\s+states|north\s+america|canada|"
    r"uk|u\.k\.|united\s+kingdom|great\s+britain|england|london|europe|eu|"
    r"emea|apac|asia|australia|new\s+zealand|germany|berlin|austria|france|"
    r"paris|spain|madrid|netherlands|amsterdam|ireland|dublin|poland|india|"
    r"singapore|japan|tokyo|argentina|mexico|colombia|chile|portugal|sweden|"
    r"switzerland|israel)\b|"
    r",\s*(?:al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|"
    r"mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|"
    r"vt|va|wa|wv|wi|wy|dc)\b",
    re.IGNORECASE,
)

_BRAZIL_LATAM_EXCLUSION_RE = re.compile(
    r"\b(?:excluding|not\s+(?:available|open)\s+in|outside\s+of|except)\s+"
    r"(?:brazil|brasil|latam|latin\s+america|south\s+america)\b",
    re.IGNORECASE,
)

_DESC_RESIDENCY_LOCK_RE = re.compile(
    r"\b(?:us\s+citizens?\s+only|us\s+residents?\s+only|"
    r"must\s+(?:be\s+located|reside)\s+in\s+the\s+(?:us|u\.s\.|united\s+states|uk|eu)|"
    r"only\s+open\s+to\s+candidates\s+in\s+(?:the\s+)?(?:us|united\s+states|uk|canada)|"
    r"authorized\s+to\s+work\s+in\s+the\s+united\s+states\s+(?:without\s+sponsorship\s+)?only|"
    r"(?:us|uk|canada|eu)\s+only)\b",
    re.IGNORECASE,
)


def get_shared_http_client() -> ResilientHTTPClient:
    """Retorna cliente HTTP compartilhado com rate-limiting e cache TTL."""
    global _default_client
    if _default_client is None:
        _default_client = ResilientHTTPClient()
    return _default_client


def fetch_raw_url(
    url: str,
    timeout: int = 12,
    use_cache: bool = True,
    headers: dict[str, str] | None = None,
    client: ResilientHTTPClient | None = None,
) -> bytes | None:
    """Realiza requisição HTTP GET resiliente retornando bytes ou None em caso de falha."""
    if client is not None:
        return client.get_bytes(url, headers=headers, use_cache=use_cache)
    shared = get_shared_http_client()
    if timeout != shared.timeout:
        with ResilientHTTPClient(timeout=float(timeout), use_cache=use_cache) as custom:
            return custom.get_bytes(url, headers=headers, use_cache=use_cache)
    return shared.get_bytes(url, headers=headers, use_cache=use_cache)


def clean_html(text: str | None, preserve_newlines: bool = False) -> str:
    """Decodifica entidades HTML e remove tags preservando texto legível."""
    if not text:
        return ""
    unescaped = html.unescape(text)
    if preserve_newlines:
        with_breaks = re.sub(
            r"<\s*(?:br\s*/?|/?p(?:\s+[^>]*)?|/?div(?:\s+[^>]*)?|/?li(?:\s+[^>]*)?|/?tr(?:\s+[^>]*)?)\s*>",
            "\n",
            unescaped,
            flags=re.IGNORECASE,
        )
        stripped = re.sub(r"<[^>]+>", " ", with_breaks)
        decoded = html.unescape(stripped)
        lines = [" ".join(line.split()) for line in decoded.splitlines()]
        cleaned_lines: list[str] = []
        for line in lines:
            if line:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
        return "\n".join(cleaned_lines).strip()

    stripped = re.sub(r"<[^>]+>", " ", unescaped)
    decoded = html.unescape(stripped)
    return " ".join(decoded.split())


def make_deterministic_id(prefix: str, key: str) -> str:
    """Gera identificador determinístico baseado em SHA-256 (independente de PYTHONHASHSEED)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def normalize_contract_type(value: Any) -> str:
    """Normaliza tipos de contrato vindos como listas ou strings literais."""
    if value is None:
        return "Remote"
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(items) if items else "Remote"
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                items = [str(v).strip() for v in parsed if str(v).strip()]
                return ", ".join(items) if items else "Remote"
        except Exception:
            pass
    return text or "Remote"


def _has_positive_number(val: Any) -> bool:
    if val is None:
        return False
    text = str(val).strip()
    if not text:
        return False
    try:
        return float(text) > 0
    except ValueError:
        return True


def format_salary_range(min_val: Any, max_val: Any, currency: str = "") -> str:
    """Formata faixa salarial ignorando limites vazios ou zerados."""
    curr = str(currency or "").strip()
    has_min = _has_positive_number(min_val)
    has_max = _has_positive_number(max_val)

    if has_min and has_max:
        return f"{min_val}-{max_val} {curr}".strip()
    if has_min:
        return f"From {min_val} {curr}".strip()
    if has_max:
        return f"Up to {max_val} {curr}".strip()
    return "Não informado"


def is_location_eligible(location: str, description: str = "") -> bool:
    """Verifica se a vaga aceita profissionais no Brasil / LATAM / Worldwide."""
    loc = (location or "").strip()
    desc = description or ""

    if _BRAZIL_LATAM_EXCLUSION_RE.search(f"{loc} {desc}"):
        return False

    if _ANYWHERE_SCOPED_RE.search(loc) and not re.search(
        r"\b(?:brazil|brasil|latam|latin\s+america|south\s+america|worldwide|global)\b",
        loc,
        re.IGNORECASE,
    ):
        return False

    if _ELIGIBLE_LOCATION_RE.search(loc):
        return True

    if loc and _BLOCKED_LOCATION_RE.search(loc):
        return False

    if _DESC_RESIDENCY_LOCK_RE.search(desc) and not _ELIGIBLE_LOCATION_RE.search(desc):
        return False

    return True
