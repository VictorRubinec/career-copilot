"""Compilador corporativo de currículos em PDF A4 via Playwright Chromium headless."""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter

from ..config import atomic_write_bytes, get_logger, get_resumes_output_dir
from ..models import CandidateProfile, CompiledPDFResult, PDFMetadata
from .resume_calibrator import calibrate_resume_for_job

logger = get_logger(__name__)

GOOGLE_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&'
    'family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
)

CORPORATE_A4_CSS = """
@page {
  size: A4 portrait;
  margin: 14mm 15mm 14mm 15mm;
}

* {
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
  background: #ffffff;
  color: #1e293b;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  font-size: 9.8pt;
  line-height: 1.44;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

main.resume-document {
  width: 100%;
  max-width: 100%;
}

.resume-header {
  padding-bottom: 8pt;
  margin-bottom: 10pt;
  border-bottom: 1.5pt solid #1e3a8a;
  break-inside: avoid;
  page-break-inside: avoid;
}

h1 {
  margin: 0 0 3pt 0;
  font-size: 18pt;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #0f172a;
  break-after: avoid;
  page-break-after: avoid;
}

.headline {
  margin: 0 0 4pt 0;
  font-size: 10.6pt;
  font-weight: 600;
  color: #1e3a8a;
}

.contact-line {
  margin: 1.5pt 0 0 0;
  font-size: 8.8pt;
  color: #475569;
}

.resume-section {
  margin-top: 10pt;
}

h2 {
  margin: 0 0 5pt 0;
  padding-bottom: 2.5pt;
  font-size: 10.5pt;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #1e3a8a;
  border-bottom: 0.75pt solid #cbd5e1;
  break-after: avoid;
  page-break-after: avoid;
}

.experience-entry {
  margin-bottom: 8pt;
  break-inside: avoid;
  page-break-inside: avoid;
}

h3 {
  margin: 4pt 0 1.5pt 0;
  font-size: 10pt;
  font-weight: 600;
  color: #0f172a;
  break-after: avoid;
  page-break-after: avoid;
}

.period {
  margin: 0 0 3pt 0;
  font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, 'Courier New', monospace;
  font-size: 8.4pt;
  font-weight: 500;
  color: #475569;
}

p {
  margin: 0 0 4.5pt 0;
  orphans: 3;
  widows: 3;
  break-inside: avoid;
}

ul {
  margin: 2pt 0 6pt 0;
  padding-left: 14pt;
}

li {
  margin: 0 0 2.5pt 0;
  orphans: 3;
  widows: 3;
  break-inside: avoid;
}

a {
  color: #1d4ed8;
  text-decoration: none;
}

code, .meta-mono {
  font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, 'Courier New', monospace;
  font-size: 8.6pt;
  background: #f1f5f9;
  color: #0f172a;
  padding: 0.5pt 3pt;
  border-radius: 2pt;
}
""".strip()

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_SAFE_URL_RE = re.compile(r"^(?:https?://|mailto:)", re.IGNORECASE)
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_ITALIC_ONLY_LINE_RE = re.compile(r"^\*([^*]+)\*$")
_HR_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")


def _slugify(value: str, max_len: int = 40) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return slug[:max_len].strip("_")


def build_resume_metadata(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any] | None = None,
) -> PDFMetadata:
    """Constrói metadados corporativos embutidos para o arquivo PDF."""
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )
    job = job_data or {}
    author = profile.candidato.nome or "Candidato"
    titulo_vaga = str(job.get("titulo") or profile.candidato.titulo_principal or "Software Engineer").strip()
    empresa = str(job.get("empresa") or "").strip()

    title = f"{author} — {titulo_vaga}"
    subject = (
        f"Currículo ATS otimizado para {titulo_vaga} ({empresa})"
        if empresa
        else f"Currículo Profissional ATS — {titulo_vaga}"
    )

    seen: set[str] = set()
    keywords: list[str] = []
    raw_terms = [
        *[str(m) for m in job.get("matches_stack", [])],
        *profile.competencias.principais,
        *profile.competencias.secundarias,
    ]
    for term in raw_terms:
        cleaned = term.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            keywords.append(cleaned)
        if len(keywords) >= 15:
            break

    return PDFMetadata(
        title=title,
        author=author,
        subject=subject,
        keywords=keywords,
    )


def build_default_pdf_filename(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any] | None = None,
) -> str:
    """Gera nome de arquivo determinístico e limpo para o currículo A4."""
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )
    job = job_data or {}
    name_slug = _slugify(profile.candidato.nome, max_len=24) or "candidato"
    role_slug = _slugify(
        str(job.get("titulo") or profile.candidato.titulo_principal or "resume"),
        max_len=28,
    )
    company_slug = _slugify(str(job.get("empresa") or ""), max_len=20)
    parts = ["cv", name_slug, role_slug]
    if company_slug:
        parts.append(company_slug)
    return "_".join(part for part in parts if part)[:80].strip("_") + ".pdf"


def _format_inline_markdown(text: str) -> str:
    """Converte links, código, negrito e itálico em HTML seguro após escaping."""
    escaped = html.escape(text, quote=True)
    tokens: list[str] = []

    def _stash(fragment: str) -> str:
        idx = len(tokens)
        tokens.append(fragment)
        return f"\x00MDTOK{idx}\x00"

    def _replace_code(match: re.Match[str]) -> str:
        return _stash(f"<code>{match.group(1)}</code>")

    def _replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        raw_url = html.unescape(match.group(2)).strip()
        if _SAFE_URL_RE.match(raw_url):
            safe_href = html.escape(raw_url, quote=True)
            return _stash(f'<a href="{safe_href}">{label}</a>')
        return label

    intermediate = _CODE_RE.sub(_replace_code, escaped)
    intermediate = _LINK_RE.sub(_replace_link, intermediate)
    intermediate = _BOLD_RE.sub(r"<strong>\1</strong>", intermediate)
    intermediate = _ITALIC_RE.sub(r"<em>\1</em>", intermediate)

    for idx, fragment in enumerate(tokens):
        intermediate = intermediate.replace(f"\x00MDTOK{idx}\x00", fragment)
    return intermediate


def markdown_to_resume_html_body(resume_markdown: str) -> str:
    """
    Converte currículo Markdown em HTML semântico linear de coluna única,
    preservando leitura sequencial 100% compatível com parsers ATS.
    """
    out: list[str] = []
    in_header = False
    in_section = False
    in_article = False
    in_list = False
    saw_headline = False
    just_opened_article = False

    def _close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def _close_article() -> None:
        nonlocal in_article, just_opened_article
        _close_list()
        if in_article:
            out.append("</article>")
            in_article = False
        just_opened_article = False

    def _close_section() -> None:
        nonlocal in_section
        _close_article()
        if in_section:
            out.append("</section>")
            in_section = False

    def _close_header() -> None:
        nonlocal in_header
        _close_list()
        if in_header:
            out.append("</header>")
            in_header = False

    for raw_line in resume_markdown.splitlines():
        line = raw_line.strip()
        if not line:
            _close_list()
            continue

        if _HR_RE.match(line):
            _close_list()
            if in_header:
                _close_header()
            continue

        if line.startswith("# ") and not line.startswith("## "):
            _close_section()
            _close_header()
            out.append('<header class="resume-header">')
            out.append(f"<h1>{_format_inline_markdown(line[2:].strip())}</h1>")
            in_header = True
            saw_headline = False
            continue

        if line.startswith("## ") and not line.startswith("### "):
            _close_header()
            _close_section()
            out.append('<section class="resume-section">')
            out.append(f"<h2>{_format_inline_markdown(line[3:].strip())}</h2>")
            in_section = True
            continue

        if line.startswith("### "):
            _close_header()
            if not in_section:
                out.append('<section class="resume-section">')
                in_section = True
            _close_article()
            out.append('<article class="experience-entry">')
            out.append(f"<h3>{_format_inline_markdown(line[4:].strip())}</h3>")
            in_article = True
            just_opened_article = True
            continue

        if line.startswith("- ") or line.startswith("* "):
            just_opened_article = False
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_format_inline_markdown(line[2:].strip())}</li>")
            continue

        _close_list()

        if in_header:
            if not saw_headline:
                cleaned = line.strip("*").strip()
                out.append(f'<p class="headline">{_format_inline_markdown(cleaned)}</p>')
                saw_headline = True
            else:
                out.append(f'<p class="contact-line">{_format_inline_markdown(line)}</p>')
            continue

        if just_opened_article:
            period_match = _ITALIC_ONLY_LINE_RE.match(line)
            if period_match:
                out.append(f'<p class="period">{html.escape(period_match.group(1).strip())}</p>')
                just_opened_article = False
                continue

        just_opened_article = False
        out.append(f"<p>{_format_inline_markdown(line)}</p>")

    _close_header()
    _close_section()
    return "\n".join(out)


def render_resume_html(
    resume_markdown: str,
    metadata: PDFMetadata,
    load_web_fonts: bool = True,
) -> str:
    """Renderiza documento HTML5 completo com estilo corporativo A4 e metadados."""
    body_html = markdown_to_resume_html_body(resume_markdown)
    fonts_block = GOOGLE_FONTS_LINK if load_web_fonts else ""
    keywords_str = ", ".join(metadata.keywords)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="pt-BR">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{html.escape(metadata.title)}</title>\n"
        f'<meta name="author" content="{html.escape(metadata.author, quote=True)}">\n'
        f'<meta name="description" content="{html.escape(metadata.subject, quote=True)}">\n'
        f'<meta name="keywords" content="{html.escape(keywords_str, quote=True)}">\n'
        f'<meta name="generator" content="{html.escape(metadata.creator, quote=True)}">\n'
        f"{fonts_block}\n"
        f"<style>\n{CORPORATE_A4_CSS}\n</style>\n"
        "</head>\n"
        "<body>\n"
        '<main class="resume-document">\n'
        f"{body_html}\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def _render_html_sync_playwright(
    html_content: str,
    load_web_fonts: bool = True,
    font_timeout_ms: int = 2000,
) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html_content, wait_until="domcontentloaded")
            if load_web_fonts:
                try:
                    page.evaluate(
                        "(ms) => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, ms))])",
                        font_timeout_ms,
                    )
                except Exception as exc:
                    logger.warning("Aviso ao aguardar fontes web no PDF: %s", exc)
            page.emulate_media(media="print")
            return page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={
                    "top": "14mm",
                    "right": "15mm",
                    "bottom": "14mm",
                    "left": "15mm",
                },
                outline=True,
                tagged=True,
            )
        finally:
            browser.close()


def render_html_to_pdf_bytes(
    html_content: str,
    load_web_fonts: bool = True,
    font_timeout_ms: int = 2000,
) -> bytes:
    """
    Compila HTML corporativo em PDF A4 via Playwright Chromium headless.
    Faz offload automático para thread dedicada quando chamado dentro de um event loop asyncio.
    """
    try:
        asyncio.get_running_loop()
        in_running_loop = True
    except RuntimeError:
        in_running_loop = False

    if not in_running_loop:
        return _render_html_sync_playwright(
            html_content,
            load_web_fonts=load_web_fonts,
            font_timeout_ms=font_timeout_ms,
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            _render_html_sync_playwright,
            html_content,
            load_web_fonts,
            font_timeout_ms,
        ).result()


def _stamp_metadata_and_inspect(
    pdf_bytes: bytes,
    metadata: PDFMetadata,
    expected_tokens: list[str],
) -> tuple[bytes, int, bool]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)
    writer.add_metadata(
        {
            "/Title": metadata.title,
            "/Author": metadata.author,
            "/Subject": metadata.subject,
            "/Keywords": ", ".join(metadata.keywords),
            "/Creator": metadata.creator,
            "/Producer": "Career Copilot / Chromium Headless",
        }
    )

    out_buf = io.BytesIO()
    writer.write(out_buf)
    final_bytes = out_buf.getvalue()

    final_reader = PdfReader(io.BytesIO(final_bytes))
    paginas = max(1, len(final_reader.pages))
    extracted_text = "\n".join((page.extract_text() or "") for page in final_reader.pages)
    extracted_lower = extracted_text.lower()

    has_text = bool(extracted_text.strip())
    matches_expected = (
        any(tok.lower() in extracted_lower for tok in expected_tokens if tok)
        if expected_tokens
        else True
    )
    ats_legivel = has_text and matches_expected
    return final_bytes, paginas, ats_legivel


def inspect_pdf_ats_readability(pdf_path: str | Path) -> dict[str, Any]:
    """Inspeciona arquivo PDF gravado em disco quanto a dimensões A4, metadados e leitura ATS."""
    target = Path(pdf_path)
    reader = PdfReader(str(target))
    paginas = len(reader.pages)
    first_box = reader.pages[0].mediabox if paginas > 0 else None
    dimensoes_pt = (
        (round(float(first_box.width), 2), round(float(first_box.height), 2))
        if first_box is not None
        else (0.0, 0.0)
    )
    raw_meta = reader.metadata or {}
    metadados = {str(k): str(v) for k, v in raw_meta.items()}
    texto_extraido = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    return {
        "paginas": paginas,
        "dimensoes_pt": dimensoes_pt,
        "metadados": metadados,
        "texto_extraido": texto_extraido,
        "caracteres_extraidos": len(texto_extraido),
        "ats_legivel": len(texto_extraido) > 0,
    }


def compile_resume_to_pdf(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any] | None = None,
    resume_markdown: str | None = None,
    output_path: str | Path | None = None,
    save_html: bool = False,
    load_web_fonts: bool = True,
    pdf_renderer: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    """
    Compila currículo Markdown em PDF A4 corporativo via Playwright Chromium headless,
    embutindo metadados corporativos e validando legibilidade por parsers ATS.
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )
    job = job_data or {}

    titulo_vaga = str(job.get("titulo") or profile.candidato.titulo_principal or "Software Engineer")
    empresa = str(job.get("empresa") or "Geral")
    vaga_alvo = f"{titulo_vaga} ({empresa})"

    if resume_markdown is None:
        calibrated = calibrate_resume_for_job(profile, job)
        resume_md = calibrated["curriculo_markdown"]
    else:
        resume_md = resume_markdown

    metadata = build_resume_metadata(profile, job)
    html_content = render_resume_html(
        resume_md,
        metadata=metadata,
        load_web_fonts=load_web_fonts,
    )

    if pdf_renderer is not None:
        raw_pdf_bytes = pdf_renderer(html_content)
    else:
        raw_pdf_bytes = render_html_to_pdf_bytes(
            html_content,
            load_web_fonts=load_web_fonts,
        )

    expected_tokens = [
        tok
        for tok in (
            profile.candidato.nome.split()[0] if profile.candidato.nome else "",
            profile.candidato.contato.email,
            *(profile.competencias.principais[:2]),
        )
        if tok
    ]

    final_pdf_bytes, paginas, ats_legivel = _stamp_metadata_and_inspect(
        raw_pdf_bytes,
        metadata=metadata,
        expected_tokens=expected_tokens,
    )

    if output_path is not None:
        target_pdf = Path(output_path)
    else:
        target_pdf = get_resumes_output_dir() / build_default_pdf_filename(profile, job)

    if target_pdf.suffix.lower() != ".pdf":
        target_pdf = target_pdf.with_suffix(".pdf")

    atomic_write_bytes(target_pdf, final_pdf_bytes)

    html_saved_path: str | None = None
    if save_html:
        target_html = target_pdf.with_suffix(".html")
        atomic_write_bytes(target_html, html_content.encode("utf-8"))
        html_saved_path = str(target_html)

    digest = hashlib.sha256(final_pdf_bytes).hexdigest()
    result = CompiledPDFResult(
        vaga_alvo=vaga_alvo,
        pdf_path=str(target_pdf),
        html_path=html_saved_path,
        tamanho_bytes=len(final_pdf_bytes),
        paginas=paginas,
        ats_legivel=ats_legivel,
        metadados=metadata,
        sha256=digest,
    )
    return result.model_dump()
