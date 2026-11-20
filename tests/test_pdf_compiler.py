import asyncio
from pathlib import Path

from src.tailor.pdf_compiler import (
    build_default_pdf_filename,
    build_resume_metadata,
    compile_resume_to_pdf,
    inspect_pdf_ats_readability,
    markdown_to_resume_html_body,
    render_resume_html,
)


def _sample_profile() -> dict:
    return {
        "candidato": {
            "nome": "Lucas Almeida França",
            "titulo_principal": "Analista de Automação & Desenvolvedor Python / Backend",
            "localizacao": "São Paulo, SP - Brasil (UTC-3)",
            "contato": {
                "email": "lucas.teste@example.com",
                "telefone": "+55 (11) 99999-0000",
                "linkedin": "https://www.linkedin.com/in/lucas-teste",
                "github": "https://github.com/lucas-teste",
                "portfolio": "",
            },
        },
        "competencias": {
            "principais": ["Python", "FastAPI", "Playwright", "Docker", "PostgreSQL", "SQL"],
            "secundarias": ["GitHub Actions", "Linux", "Shell Script"],
            "idiomas": {"portugues": "Nativo", "ingles": "Técnico / Avançado"},
        },
        "horario_trabalho_desejado": {
            "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00 (BRT)"},
            "carga_semanal_horas": 20,
            "permite_reunioes_horario_comercial": False,
        },
        "historico_profissional": [
            {
                "empresa": "CloudOps Corp",
                "cargo": "Backend & Automation Engineer",
                "periodo": "Maio/2025 – Julho/2026",
                "atividades": [
                    "Reduziu incidentes em produção em 42% ao implementar suíte E2E em Playwright e pytest com CI/CD.",
                    "Construiu pipelines ETL assíncronos em Python e PostgreSQL processando 120k registros por janela.",
                ],
            },
            {
                "empresa": "InfraData Ltda",
                "cargo": "Analista DevOps & Automação",
                "periodo": "Março/2023 – Fevereiro/2025",
                "atividades": [
                    "Automatizou health checks em Linux/Shell e Docker elevando disponibilidade para 99.9%."
                ],
            },
        ],
        "formacao_e_certificacoes": [
            {"titulo": "Bacharelado em Ciência da Computação", "detalhe": ""},
            {"titulo": "Six Sigma White Belt", "detalhe": "Melhoria Contínua"},
        ],
    }


def test_markdown_to_html_semantic_structure_and_xss_safety():
    md = """# Ana <script>alert(1)</script> Dev
**Python & Playwright Engineer**
São Paulo, BR • ana@example.com
[LinkedIn](https://linkedin.com/in/ana) • [XSS](javascript:alert(1))

---

## Resumo Profissional
Engenheira com foco em `FastAPI` e **automação assíncrona** com *Playwright*.

## Experiência Profissional
### Automation Engineer — AsyncCorp
*2024 - 2026*

- Reduziu falhas em 50% com suíte E2E.
"""
    body = markdown_to_resume_html_body(md)

    assert '<header class="resume-header">' in body
    assert '<section class="resume-section">' in body
    assert '<article class="experience-entry">' in body
    assert '<p class="period">2024 - 2026</p>' in body
    assert "<ul>" in body and "<li>Reduziu falhas em 50% com suíte E2E.</li>" in body
    assert "<code>FastAPI</code>" in body
    assert "<strong>automação assíncrona</strong>" in body
    assert "<em>Playwright</em>" in body
    assert '<a href="https://linkedin.com/in/ana">LinkedIn</a>' in body
    assert "<script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "javascript:" not in body


def test_render_resume_html_corporate_css_and_fonts():
    profile = _sample_profile()
    meta = build_resume_metadata(
        profile, {"titulo": "Python Engineer", "empresa": "GitLab", "matches_stack": ["python"]}
    )
    html_with_fonts = render_resume_html("# Lucas\n\n## Resumo\nTexto.", meta, load_web_fonts=True)
    html_offline = render_resume_html("# Lucas\n\n## Resumo\nTexto.", meta, load_web_fonts=False)

    assert "fonts.googleapis.com" in html_with_fonts
    assert "fonts.googleapis.com" not in html_offline
    for css_rule in (
        "@page {",
        "size: A4 portrait;",
        "'Inter'",
        "'JetBrains Mono'",
        "break-after: avoid;",
        "break-inside: avoid;",
        "orphans: 3;",
        "widows: 3;",
    ):
        assert css_rule in html_offline
    assert '<meta name="author" content="Lucas Almeida França">' in html_offline


def test_build_default_pdf_filename_and_metadata():
    profile = _sample_profile()
    job = {
        "titulo": "Sênior Python & Automação (Contractor)",
        "empresa": "AsyncLabs Global",
        "matches_stack": ["FastAPI", "Python", "Docker"],
    }
    filename = build_default_pdf_filename(profile, job)
    meta = build_resume_metadata(profile, job)

    assert filename.startswith("cv_lucas_almeida")
    assert filename.endswith(".pdf")
    assert " " not in filename
    assert meta.author == "Lucas Almeida França"
    assert "AsyncLabs Global" in meta.subject
    assert meta.keywords[0] == "FastAPI"
    assert len(meta.keywords) <= 15


def test_compile_resume_to_pdf_real_playwright_chromium_a4_and_ats(tmp_path: Path):
    profile = _sample_profile()
    job = {
        "titulo": "Python Automation & Backend Contractor",
        "empresa": "GitLab",
        "matches_stack": ["python", "fastapi", "playwright", "docker", "postgresql"],
    }
    out_pdf = tmp_path / "cv_real.pdf"

    res = compile_resume_to_pdf(
        profile,
        job_data=job,
        output_path=out_pdf,
        save_html=True,
        load_web_fonts=False,
    )

    assert out_pdf.exists()
    assert out_pdf.read_bytes().startswith(b"%PDF-")
    assert res["html_path"] is not None and Path(res["html_path"]).exists()
    assert res["tamanho_bytes"] > 5000
    assert res["paginas"] >= 1
    assert res["ats_legivel"] is True
    assert len(res["sha256"]) == 64

    inspected = inspect_pdf_ats_readability(out_pdf)
    width_pt, height_pt = inspected["dimensoes_pt"]
    assert 592.0 <= width_pt <= 598.0
    assert 838.0 <= height_pt <= 846.0
    assert inspected["metadados"].get("/Author") == "Lucas Almeida França"
    assert "GitLab" in inspected["metadados"].get("/Subject", "")
    assert "Career Copilot" in inspected["metadados"].get("/Creator", "")

    extracted = inspected["texto_extraido"]
    for token in (
        "Lucas Almeida",
        "lucas.teste@example.com",
        "Python",
        "FastAPI",
        "Playwright",
        "Docker",
        "CloudOps Corp",
    ):
        assert token in extracted


def test_compile_resume_to_pdf_inside_running_asyncio_loop(tmp_path: Path):
    profile = _sample_profile()
    out_pdf = tmp_path / "async_loop_cv.pdf"

    async def _run_in_loop() -> dict:
        return compile_resume_to_pdf(
            profile,
            job_data={"titulo": "Async Python Engineer", "empresa": "AsyncCo"},
            output_path=out_pdf,
            load_web_fonts=False,
        )

    res = asyncio.run(_run_in_loop())
    assert out_pdf.exists()
    assert res["ats_legivel"] is True
    assert res["paginas"] >= 1
