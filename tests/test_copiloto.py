from pathlib import Path

import pytest

from src.config import get_applications_log_path
from src.copiloto import (
    build_application_payload,
    detect_external_gate,
    prepare_assisted_application,
)


def _sample_profile() -> dict:
    return {
        "candidato": {
            "nome": "Lucas Almeida França",
            "titulo_principal": "Analista de Automação & Desenvolvedor Python / Backend",
            "localizacao": "São Paulo, SP - Brasil",
            "contato": {
                "email": "lucas.teste@example.com",
                "telefone": "+55 11 99999-0000",
                "linkedin": "https://www.linkedin.com/in/lucas-teste",
                "github": "https://github.com/lucas-teste",
                "portfolio": "https://lucas.dev.example",
            },
        },
        "preferencias_carreira": {
            "regimes_contratuais": ["Contractor B2B (USD/EUR)", "PJ Flexível (Brasil)"],
            "remuneracao_minima": {
                "usd_hora": 18.0,
                "usd_mensal": 1800.0,
                "brl_hora": 50.0,
                "brl_mensal": 4000.0,
            },
        },
        "horario_trabalho_desejado": {
            "timezone_candidato": "America/Sao_Paulo (UTC-3)",
            "janela_disponivel": {
                "segunda_a_sexta": "19:00 - 00:00 (BRT)",
                "finais_de_semana": "Sob demanda",
            },
            "carga_semanal_horas": 20,
            "permite_reunioes_horario_comercial": False,
        },
        "competencias": {
            "principais": ["Python", "Playwright", "FastAPI", "Docker"],
            "idiomas": {"portugues": "Nativo", "ingles": "Técnico / Fluente assíncrono"},
        },
        "historico_profissional": [
            {
                "empresa": "CloudOps Corp",
                "cargo": "Backend & Automation Engineer",
                "periodo": "2024 - 2026",
                "atividades": ["Automação com Python e Playwright."],
            }
        ],
    }


def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    browser_dir = tmp_path / "browser_profile"
    monkeypatch.setenv("CAREER_COPILOT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CAREER_COPILOT_BROWSER_PROFILE_DIR", str(browser_dir))
    pdf_file = tmp_path / "resume_lucas.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%Mock resume bytes\n%%EOF\n")
    return pdf_file


def test_build_application_payload_splits_name_and_screening_answers():
    profile = _sample_profile()
    intl_job = {
        "id": "ghb_1",
        "titulo": "Python Automation Engineer",
        "empresa": "AsyncLabs",
        "origem": "Internacional (USD/EUR)",
        "localizacao": "Worldwide",
        "url": "https://boards.greenhouse.io/asynclabs/jobs/1",
    }
    payload_en = build_application_payload(
        profile,
        intl_job,
        custom_answers={"visa_sponsorship": "Not required (B2B Contractor)"},
    )
    assert payload_en.primeiro_nome == "Lucas"
    assert payload_en.sobrenome == "Almeida França"
    assert "Subject: Application:" in payload_en.carta_apresentacao
    assert "$18/hour USD" in payload_en.respostas_triagem["pretensao_salarial"]
    assert "19:00 - 00:00 (BRT)" in payload_en.respostas_triagem["disponibilidade_horario"]
    assert payload_en.respostas_triagem["visa_sponsorship"] == "Not required (B2B Contractor)"

    nat_job = {
        "id": "gh_2",
        "titulo": "Desenvolvedor Python PJ",
        "empresa": "BrasilAsync",
        "origem": "Nacional (BRL / PJ)",
        "localizacao": "Brasil (100% Remoto)",
        "url": "https://github.com/backend-br/vagas/issues/2",
    }
    payload_pt = build_application_payload(profile, nat_job)
    assert "Assunto: Candidatura:" in payload_pt.carta_apresentacao
    assert "R$ 50/h" in payload_pt.respostas_triagem["pretensao_salarial"]


def test_detect_external_gate_captcha_and_login_walls():
    assert "reCAPTCHA" in (
        detect_external_gate("https://apply.example.com", '<div class="g-recaptcha"></div>') or ""
    )
    assert "hCaptcha" in (
        detect_external_gate("https://apply.example.com", '<div class="h-captcha"></div>') or ""
    )
    assert "Cloudflare Turnstile" in (
        detect_external_gate("https://apply.example.com", '<div class="cf-turnstile"></div>') or ""
    )
    assert "login" in (
        detect_external_gate(
            "https://jobs.example.com/signin",
            '<form><input type="email"/><input type="password"/></form>',
        )
        or ""
    ).lower()
    clean_html = '<form><input name="first_name"/><input type="file" name="resume"/></form>'
    assert detect_external_gate("https://boards.greenhouse.io/co/jobs/1", clean_html) is None


def test_schedule_conflict_blocks_application_by_default_and_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dummy_pdf = _isolated_env(tmp_path, monkeypatch)
    profile = _sample_profile()
    daytime_job = {
        "id": "bad_1",
        "titulo": "Python Developer",
        "empresa": "StrictCorp",
        "localizacao": "USA",
        "tipo_contrato": "Full-Time",
        "url": "https://example.com/strict-job",
        "descricao": "Mandatory 9-5 core hours, daily standup at 10am and on-site presence.",
    }

    blocked = prepare_assisted_application(
        profile,
        daytime_job,
        pdf_path=dummy_pdf,
        dry_run=True,
    )
    assert blocked["status"] == "BLOQUEADO_CONFLITO_HORARIO"
    assert blocked["submetido_automaticamente"] is False
    assert blocked["compatibilidade_horario"]["status"] == "INCOMPATIVEL"

    allowed = prepare_assisted_application(
        profile,
        daytime_job,
        pdf_path=dummy_pdf,
        dry_run=True,
        allow_schedule_conflict=True,
    )
    assert allowed["status"] == "DRY_RUN_PREPARADO"
    assert allowed["submetido_automaticamente"] is False


def test_idempotent_duplicate_detection_in_applications_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dummy_pdf = _isolated_env(tmp_path, monkeypatch)
    profile = _sample_profile()
    job = {
        "id": "async_1",
        "titulo": "Python Contractor",
        "empresa": "AsyncCo",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "url": "https://example.com/jobs/async-1/",
        "descricao": "Async-first flexible hours Python contractor.",
    }

    first = prepare_assisted_application(profile, job, pdf_path=dummy_pdf, dry_run=True)
    assert first["duplicata_detectada"] is False
    assert get_applications_log_path().exists()

    # Mesma URL sem barra final -> detecta duplicata idempotentemente
    job_same = {**job, "url": "https://example.com/jobs/async-1"}
    second = prepare_assisted_application(profile, job_same, pdf_path=dummy_pdf, dry_run=True)
    assert second["duplicata_detectada"] is True
    assert second["submetido_automaticamente"] is False


def test_real_playwright_autofill_pdf_upload_and_human_pause_never_submits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dummy_pdf = _isolated_env(tmp_path, monkeypatch)
    profile = _sample_profile()

    ats_form_html = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Apply — AsyncLabs</title></head>
<body>
  <script>window.__submitted = false;</script>
  <form onsubmit="event.preventDefault(); window.__submitted = true;">
    <input id="first_name" name="first_name" type="text" required />
    <input id="last_name" name="last_name" type="text" required />
    <input id="email" name="email" type="email" required />
    <input id="phone" name="phone" type="tel" />
    <input id="linkedin" name="linkedin_url" type="url" placeholder="LinkedIn URL" />
    <input id="github" name="github_url" type="url" placeholder="GitHub URL" />
    <input id="location" name="location" type="text" placeholder="Location" />
    <input id="resume" name="resume" type="file" accept=".pdf" required />
    <textarea id="cover_letter" name="cover_letter"></textarea>
    <label for="tz_q">Timezone and async hours availability</label>
    <textarea id="tz_q" name="question_timezone" placeholder="Your timezone and availability"></textarea>
    <select id="referral" name="referral" required>
      <option value="">-- Select --</option>
      <option value="hn">Hacker News</option>
    </select>
    <button type="submit" id="submit_btn">Submit Application</button>
  </form>
</body>
</html>
"""
    form_path = tmp_path / "ats_form.html"
    form_path.write_text(ats_form_html, encoding="utf-8")

    job = {
        "id": "local_ats_1",
        "titulo": "Python & Playwright Contractor",
        "empresa": "AsyncLabs",
        "origem": "Internacional (USD)",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "url": form_path.resolve().as_uri(),
        "descricao": "Async-first flexible hours Python Playwright contractor.",
    }

    dom_snapshot: dict = {}

    def _inspect_on_pause(page, draft_result) -> None:
        dom_snapshot["submitted"] = page.evaluate("() => window.__submitted")
        dom_snapshot["first_name"] = page.locator("#first_name").input_value()
        dom_snapshot["last_name"] = page.locator("#last_name").input_value()
        dom_snapshot["email"] = page.locator("#email").input_value()
        dom_snapshot["linkedin"] = page.locator("#linkedin").input_value()
        dom_snapshot["cover_letter"] = page.locator("#cover_letter").input_value()
        dom_snapshot["tz_q"] = page.locator("#tz_q").input_value()
        dom_snapshot["file_count"] = page.evaluate(
            "() => document.getElementById('resume').files.length"
        )
        dom_snapshot["file_name"] = page.evaluate(
            "() => document.getElementById('resume').files[0].name"
        )
        dom_snapshot["banner_exists"] = page.evaluate(
            "() => Boolean(document.getElementById('career-copilot-hitl-banner'))"
        )

    res = prepare_assisted_application(
        profile,
        job,
        pdf_path=dummy_pdf,
        headless=True,
        wait_for_human=False,
        pause_callback=_inspect_on_pause,
    )

    assert dom_snapshot["submitted"] is False
    assert dom_snapshot["first_name"] == "Lucas"
    assert dom_snapshot["last_name"] == "Almeida França"
    assert dom_snapshot["email"] == "lucas.teste@example.com"
    assert "linkedin.com" in dom_snapshot["linkedin"]
    assert "Subject: Application:" in dom_snapshot["cover_letter"]
    assert "19:00 - 00:00 (BRT)" in dom_snapshot["tz_q"]
    assert dom_snapshot["file_count"] == 1
    assert dom_snapshot["file_name"] == "resume_lucas.pdf"
    assert dom_snapshot["banner_exists"] is True

    assert res["status"] == "AGUARDANDO_REVISAO_HUMANA"
    assert res["submetido_automaticamente"] is False
    assert res["requer_confirmacao_humana"] is True
    assert "referral" in res["campos_pendentes_humano"]
    assert len(res["campos_preenchidos"]) >= 8


def test_real_playwright_pauses_on_captcha_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dummy_pdf = _isolated_env(tmp_path, monkeypatch)
    profile = _sample_profile()

    captcha_html = """<!DOCTYPE html>
<html><body>
  <h1>Verify you are human</h1>
  <div class="cf-turnstile" data-sitekey="mock"></div>
  <form><input name="email" type="email" /></form>
</body></html>
"""
    captcha_path = tmp_path / "captcha_gate.html"
    captcha_path.write_text(captcha_html, encoding="utf-8")

    job = {
        "id": "gate_1",
        "titulo": "Async Python Engineer",
        "empresa": "ProtectedCo",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "url": captcha_path.resolve().as_uri(),
        "descricao": "Async-first flexible hours Python role.",
    }

    called_pause = []
    res = prepare_assisted_application(
        profile,
        job,
        pdf_path=dummy_pdf,
        headless=True,
        wait_for_human=False,
        pause_callback=lambda page, draft: called_pause.append(draft.status),
    )

    assert called_pause == ["PAUSADO_VERIFICACAO_HUMANA"]
    assert res["status"] == "PAUSADO_VERIFICACAO_HUMANA"
    assert res["submetido_automaticamente"] is False
    assert "Cloudflare Turnstile" in (res["bloqueio_externo_detectado"] or "")
    assert res["campos_preenchidos"] == []
