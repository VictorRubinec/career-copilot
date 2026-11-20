import json
from pathlib import Path

import pytest

from src import cli, mcp_server
from src.config import save_profile
from src.tailor import pdf_compiler


def _minimal_searchable_pdf_bytes(text: str = "Tester CLI Python Playwright Docker") -> bytes:
    """Gera PDF 1.4 válido com texto extraível por pypdf para mocks rápidos de CLI/MCP."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 750 Td ({escaped}) Tj ET".encode("latin-1", errors="ignore")
    objs = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        ),
        f"4 0 obj << /Length {len(stream)} >> stream\n".encode("ascii")
        + stream
        + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def _setup_isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAREER_COPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CAREER_COPILOT_CACHE_DIR", str(tmp_path / "cache"))
    profile_path = tmp_path / "perfil.json"
    monkeypatch.setenv("CAREER_COPILOT_PROFILE_PATH", str(profile_path))
    save_profile(
        {
            "candidato": {
                "nome": "Tester CLI",
                "titulo_principal": "Python Automation Engineer",
                "localizacao": "São Paulo, BR",
                "contato": {"email": "tester@example.com"},
            },
            "competencias": {
                "principais": ["Python", "Playwright", "Docker", "SQL"],
                "idiomas": {"ingles": "Avançado"},
            },
            "horario_trabalho_desejado": {
                "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
                "carga_semanal_horas": 20,
                "permite_reunioes_horario_comercial": False,
            },
            "historico_profissional": [
                {
                    "empresa": "TestCorp",
                    "cargo": "Backend Engineer",
                    "periodo": "2025 - 2026",
                    "atividades": ["Automação em Python"],
                }
            ],
        },
        path=profile_path,
    )


def _sample_qualified_jobs() -> list[dict]:
    return [
        {
            "id": "ghb_gitlab_10",
            "fonte": "Greenhouse (gitlab)",
            "origem": "Internacional (USD/EUR)",
            "empresa": "GitLab",
            "titulo": "Python Automation Contractor",
            "localizacao": "Worldwide",
            "tipo_contrato": "Contractor",
            "salario": "Não informado",
            "url": "https://boards.greenhouse.io/gitlab/jobs/10",
            "data_publicacao": "2026-11-19",
            "descricao": "Async-first flexible hours Python Playwright Docker SQL.",
            "resumo": "Async-first Python role",
            "schedule_fit": {
                "score_horario": 100,
                "status": "COMPATIVEL",
                "classificacao_exibicao": "[COMPATÍVEL]",
                "justificativa": "Compatível com turno noturno.",
                "red_flags": [],
                "sinais_positivos": ["async-first", "flexible schedule/hours", "contractor"],
                "janela_candidato": {"segunda_a_sexta": "19:00 - 00:00"},
                "permite_reunioes_comercial": False,
            },
            "stack_score": 100,
            "matches_stack": ["docker", "playwright", "python", "sql"],
            "score_composto": 100.0,
        }
    ]


def test_cli_profile_mine_and_tailor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _setup_isolated_env(tmp_path, monkeypatch)

    cli.main(["profile", "--json"])
    prof_out = json.loads(capsys.readouterr().out)
    assert prof_out["candidato"]["nome"] == "Tester CLI"

    captured_kwargs: dict = {}

    def fake_mine(profile, **kwargs):
        captured_kwargs.update(kwargs)
        return _sample_qualified_jobs()

    monkeypatch.setattr(cli, "mine_all_opportunities", fake_mine)
    cli.main(["mine", "--fontes", "greenhouse,hackernews", "--no-cache", "--top", "5"])
    mine_out = capsys.readouterr().out
    assert captured_kwargs["fontes"] == ["greenhouse", "hackernews"]
    assert captured_kwargs["use_cache"] is False
    assert "[COMPATÍVEL]" in mine_out
    assert (tmp_path / "data" / "vagas_mineradas.json").exists()

    cli.main(["tailor", "--index", "0", "--with-review"])
    tailor_out = capsys.readouterr().out
    assert "Python Automation Contractor (GitLab)" in tailor_out
    assert "Tester CLI" in tailor_out
    assert "TestCorp" in tailor_out
    assert "BANCA EXAMINADORA (7 PERSONAS)" in tailor_out

    cli.main(["review", "--index", "0", "--json"])
    review_json = json.loads(capsys.readouterr().out)
    assert review_json["vaga_alvo"] == "Python Automation Contractor (GitLab)"
    assert len(review_json["avaliacoes"]) == 7

    custom_resume = tmp_path / "custom_cv.md"
    custom_resume.write_text(
        "# Tester CLI\n**Python Automation Engineer**\ntester@example.com\n\n"
        "## Resumo\nPython Playwright Docker SQL async-first.\n\n"
        "## Experiência\n- Reduziu falhas em 40% com pytest e Playwright em CI/CD Docker.\n",
        encoding="utf-8",
    )
    cli.main(["review", "--index", "0", "--resume", str(custom_resume)])
    review_txt = capsys.readouterr().out
    assert "BANCA EXAMINADORA (7 PERSONAS)" in review_txt
    assert "Notas Individuais" in review_txt

    monkeypatch.setattr(
        pdf_compiler,
        "render_html_to_pdf_bytes",
        lambda html, load_web_fonts=True, font_timeout_ms=2000: _minimal_searchable_pdf_bytes(),
    )
    pdf_out_path = tmp_path / "cli_export.pdf"
    cli.main(
        [
            "pdf",
            "--index",
            "0",
            "--output",
            str(pdf_out_path),
            "--save-html",
            "--offline-fonts",
            "--json",
        ]
    )
    pdf_json = json.loads(capsys.readouterr().out)
    assert pdf_out_path.exists()
    assert pdf_json["ats_legivel"] is True
    assert pdf_json["html_path"] is not None

    cli.main(["tailor", "--index", "0", "--pdf", "--offline-fonts"])
    tailor_pdf_out = capsys.readouterr().out
    assert "PDF A4 CORPORATIVO COMPILADO" in tailor_pdf_out
    assert (tmp_path / "data" / "curriculos_gerados").exists()

    cli.main(["apply", "--index", "0", "--dry-run", "--offline-fonts", "--json"])
    apply_json = json.loads(capsys.readouterr().out)
    assert apply_json["status"] == "DRY_RUN_PREPARADO"
    assert apply_json["submetido_automaticamente"] is False

    cli.main(["apply", "--url", "https://example.com/remote-job", "--dry-run", "--offline-fonts"])
    apply_txt = capsys.readouterr().out
    assert "COPILOTO HUMAN-IN-THE-LOOP" in apply_txt
    assert "Submetido Automaticamente: False" in apply_txt


def test_mcp_tools_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _setup_isolated_env(tmp_path, monkeypatch)
    assert mcp_server.mcp is not None

    prof = json.loads(mcp_server.get_career_profile())
    assert prof["candidato"]["nome"] == "Tester CLI"

    eval_res = json.loads(
        mcp_server.evaluate_job(
            "Async-first flexible hours Python & Docker contractor.",
            "Worldwide",
            "Contract",
        )
    )
    assert eval_res["horario_classificacao"] == "[COMPATÍVEL]"

    # Sem base de vagas ainda
    empty_tailor = json.loads(mcp_server.tailor_application("inexistente"))
    assert "erro" in empty_tailor

    monkeypatch.setattr(
        mcp_server, "mine_all_opportunities", lambda *a, **kw: _sample_qualified_jobs()
    )
    mine_res = json.loads(mcp_server.mine_jobs(fontes=["greenhouse"], use_cache=False))
    assert mine_res["total_encontradas"] == 1
    assert mine_res["top_15"][0]["horario_classificacao"] == "[COMPATÍVEL]"

    app_pkg = json.loads(mcp_server.tailor_application("ghb_gitlab_10"))
    assert "Tester CLI" in app_pkg["curriculo_markdown"]
    assert "GitLab" in app_pkg["cold_pitch_ingles"]

    missing_pkg = json.loads(mcp_server.tailor_application("nao_existe"))
    assert "erro" in missing_pkg

    review_by_id = json.loads(mcp_server.review_application(job_id="ghb_gitlab_10"))
    assert len(review_by_id["avaliacoes"]) == 7
    assert review_by_id["veredito"] in ("APROVADO", "REVISAR", "VETADO")

    review_adhoc = json.loads(
        mcp_server.review_application(
            job_description="Async-first remote Python Playwright Docker SQL contractor.",
            job_title="Python Automation Engineer",
            job_company="AsyncWorld",
        )
    )
    assert review_adhoc["vaga_alvo"] == "Python Automation Engineer (AsyncWorld)"
    assert len(review_adhoc["avaliacoes"]) == 7

    review_err = json.loads(mcp_server.review_application())
    assert "erro" in review_err

    monkeypatch.setattr(
        pdf_compiler,
        "render_html_to_pdf_bytes",
        lambda html, load_web_fonts=True, font_timeout_ms=2000: _minimal_searchable_pdf_bytes(),
    )
    mcp_pdf_by_id = json.loads(
        mcp_server.export_resume_pdf(job_id="ghb_gitlab_10", load_web_fonts=False)
    )
    assert Path(mcp_pdf_by_id["pdf_path"]).exists()
    assert mcp_pdf_by_id["ats_legivel"] is True

    mcp_pdf_adhoc = json.loads(
        mcp_server.export_resume_pdf(
            job_title="Python Dev",
            job_company="AsyncCo",
            output_path=str(tmp_path / "mcp_adhoc.pdf"),
            load_web_fonts=False,
        )
    )
    assert Path(mcp_pdf_adhoc["pdf_path"]).exists()

    mcp_pdf_err = json.loads(mcp_server.export_resume_pdf(job_id="nao_existe"))
    assert "erro" in mcp_pdf_err

    mcp_apply_by_id = json.loads(
        mcp_server.assist_application(
            job_id="ghb_gitlab_10",
            dry_run=True,
            load_web_fonts=False,
        )
    )
    assert mcp_apply_by_id["status"] == "DRY_RUN_PREPARADO"
    assert mcp_apply_by_id["submetido_automaticamente"] is False

    mcp_apply_adhoc = json.loads(
        mcp_server.assist_application(
            job_url="https://example.com/async-role",
            job_title="Python Contractor",
            job_company="AsyncCorp",
            job_description="Async-first flexible hours role.",
            dry_run=True,
            load_web_fonts=False,
        )
    )
    assert mcp_apply_adhoc["vaga_alvo"] == "Python Contractor (AsyncCorp)"
    assert mcp_apply_adhoc["submetido_automaticamente"] is False

    mcp_apply_err = json.loads(mcp_server.assist_application())
    assert "erro" in mcp_apply_err
