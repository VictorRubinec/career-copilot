import pytest
from pydantic import ValidationError

from src.evaluators.committee import (
    REQUIRED_PERSONA_IDS,
    build_committee_prompt,
    compute_committee_consensus,
    evaluate_application_committee,
)
from src.models import (
    CandidateProfile,
    CommitteePersonaBatch,
    PersonaEvaluation,
    PersonaId,
    ScheduleFitResult,
)


def _make_schedule_fit(status: str = "COMPATIVEL", score: int = 95) -> ScheduleFitResult:
    labels = {
        "COMPATIVEL": "[COMPATÍVEL]",
        "PARCIALMENTE_COMPATIVEL": "[PARCIALMENTE COMPATÍVEL]",
        "INCOMPATIVEL": "[INCOMPATÍVEL]",
    }
    return ScheduleFitResult(
        score_horario=score,
        status=status,  # type: ignore[arg-type]
        classificacao_exibicao=labels[status],
        justificativa="Teste de rotina.",
        red_flags=["mandatory 9-5"] if status == "INCOMPATIVEL" else [],
        sinais_positivos=["async-first"] if status == "COMPATIVEL" else [],
        janela_candidato={"segunda_a_sexta": "19:00 - 00:00"},
        permite_reunioes_comercial=False,
    )


def _make_batch(overrides: dict[PersonaId, float] | None = None) -> list[PersonaEvaluation]:
    scores: dict[PersonaId, float] = {pid: 8.5 for pid in REQUIRED_PERSONA_IDS}
    if overrides:
        scores.update(overrides)
    return [
        PersonaEvaluation(
            persona_id=pid,
            persona_nome=pid.replace("_", " ").title(),
            nota=scores[pid],
            foco_avaliacao="Critério de teste",
            pontos_fortes=["Entrega consistente"] if scores[pid] >= 7.0 else [],
            lacunas_e_riscos=["Falha crítica detectada"] if scores[pid] < 7.0 else [],
            acoes_corretivas=[f"Corrigir item de {pid}"] if scores[pid] < 8.0 else [],
            justificativa=f"Nota {scores[pid]:.1f}",
        )
        for pid in REQUIRED_PERSONA_IDS
    ]


def _base_profile() -> dict:
    return {
        "candidato": {
            "nome": "Pedro Teste",
            "titulo_principal": "Python Backend & Automation Engineer",
            "localizacao": "São Paulo, BR",
            "contato": {
                "email": "pedro.teste@example.com",
                "linkedin": "https://linkedin.com/in/pedro-teste",
                "github": "https://github.com/pedro-teste",
            },
        },
        "preferencias_carreira": {
            "senioridade_alvo": ["Mid-Level", "Contractor"],
            "regimes_contratuais": ["Contractor B2B (USD/EUR)"],
        },
        "horario_trabalho_desejado": {
            "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00 (BRT)"},
            "carga_semanal_horas": 20,
            "permite_reunioes_horario_comercial": False,
        },
        "competencias": {
            "principais": ["Python", "FastAPI", "Playwright", "Docker", "PostgreSQL", "SQL", "GitHub Actions", "Linux"],
            "secundarias": ["Monitoramento & Logs", "AWS"],
            "idiomas": {"portugues": "Nativo", "ingles": "Avançado"},
        },
        "historico_profissional": [
            {
                "empresa": "CloudOps Corp",
                "cargo": "Backend & Automation Engineer",
                "periodo": "2024 - 2026",
                "atividades": [
                    "Desenvolveu APIs REST em Python/FastAPI com cobertura de testes pytest.",
                    "Implementou pipelines ETL e scripts Playwright reduzindo incidentes em produção.",
                ],
            },
            {
                "empresa": "DataFlow Ltda",
                "cargo": "Analista DevOps & Automação",
                "periodo": "2022 - 2024",
                "atividades": [
                    "Automatizou health checks, logs e containers Docker em ambientes Linux."
                ],
            },
        ],
        "formacao_e_certificacoes": [
            {"titulo": "Bacharelado em Ciência da Computação", "detalhe": ""},
            {"titulo": "Six Sigma White Belt", "detalhe": "Melhoria contínua"},
        ],
    }


def _strong_xyz_resume() -> str:
    return """# Pedro Teste
**Python Backend & Automation Engineer**
São Paulo, BR • pedro.teste@example.com • [LinkedIn](https://linkedin.com/in/pedro-teste) • [GitHub](https://github.com/pedro-teste)

---

## Resumo Profissional
Engenheiro Python e Automação orientado a entregas assíncronas com foco em APIs REST (FastAPI), pipelines ETL em PostgreSQL, testes automatizados (pytest/Playwright) e infraestrutura Docker/CI/CD.

---

## Competências Técnicas
- **Linguagens & Frameworks:** Python, FastAPI, Playwright, Docker, PostgreSQL, SQL, GitHub Actions, Linux
- **Observabilidade & Governança:** Monitoramento, Logs estruturados, Health Checks, Documentação Assíncrona

---

## Experiência Profissional

### Backend & Automation Engineer — CloudOps Corp
*2024 - 2026*

- Reduziu falhas em produção em 42% (medido por logs e SLAs) ao implementar suíte E2E em Playwright e pytest com CI/CD no GitHub Actions.
- Acelerou pipelines ETL assíncronos em PostgreSQL e Python em 3x, processando 120k registros por janela noturna sem intervenção manual.
- Construiu APIs REST em FastAPI e workers Docker com health checks automatizados, elevando a disponibilidade para 99.9%.

### Analista DevOps & Automação — DataFlow Ltda
*2022 - 2024*

- Economizou 15 horas semanais da equipe de infraestrutura ao criar rotinas Linux/Shell de triagem proativa de logs e incidentes.
- Padronizou documentação de runbooks e revisão assíncrona de Pull Requests com tipagem estrita e Pydantic.
"""


def test_consensus_approval_and_veto_boundaries():
    sched = _make_schedule_fit()

    approved = compute_committee_consensus(_make_batch(), sched, "Python Role")
    assert approved.veredito == "APROVADO"
    assert approved.aprovado is True
    assert approved.media_geral == 8.5
    assert approved.veto.ativo is False

    # Média alta (>= 8.0), mas ATS < 7.0 -> VETO automático
    ats_vetoed = compute_committee_consensus(
        _make_batch(
            {
                "ats_screener": 6.9,
                "tech_recruiter": 9.0,
                "engineering_manager": 9.0,
                "senior_peer": 9.0,
                "product_manager": 9.0,
                "cto_head": 9.0,
                "skeptic_recruiter": 9.0,
            }
        ),
        sched,
        "Python Role",
    )
    assert ats_vetoed.media_geral >= 8.0
    assert ats_vetoed.veredito == "VETADO"
    assert ats_vetoed.aprovado is False
    assert ats_vetoed.veto.ativo is True
    assert ats_vetoed.veto.personas_vetadoras == ["ats_screener"]

    # Média alta (>= 8.0), mas Recrutador Cético < 7.0 -> VETO automático
    skeptic_vetoed = compute_committee_consensus(
        _make_batch(
            {
                "ats_screener": 9.0,
                "tech_recruiter": 9.0,
                "engineering_manager": 9.0,
                "senior_peer": 9.0,
                "product_manager": 9.0,
                "cto_head": 9.0,
                "skeptic_recruiter": 6.8,
            }
        ),
        sched,
        "Python Role",
    )
    assert skeptic_vetoed.veredito == "VETADO"
    assert skeptic_vetoed.veto.personas_vetadoras == ["skeptic_recruiter"]

    # Duplo veto (ATS e Cético < 7.0)
    dual_veto = compute_committee_consensus(
        _make_batch({"ats_screener": 5.5, "skeptic_recruiter": 6.0}),
        sched,
        "Python Role",
    )
    assert dual_veto.veredito == "VETADO"
    assert dual_veto.veto.personas_vetadoras == ["ats_screener", "skeptic_recruiter"]

    # Média < 8.0 sem veto -> REVISAR
    review_needed = compute_committee_consensus(
        _make_batch({pid: 7.5 for pid in REQUIRED_PERSONA_IDS}),
        sched,
        "Python Role",
    )
    assert review_needed.veredito == "REVISAR"
    assert review_needed.aprovado is False
    assert review_needed.veto.ativo is False


def test_committee_batch_rejects_missing_or_duplicate_personas():
    incomplete = _make_batch()[:-1]
    with pytest.raises(ValidationError):
        CommitteePersonaBatch(avaliacoes=incomplete)

    duplicated = _make_batch()
    duplicated[-1] = duplicated[0].model_copy()
    with pytest.raises(ValidationError):
        CommitteePersonaBatch(avaliacoes=duplicated)


def test_committee_end_to_end_approved_strong_xyz_resume():
    job = {
        "titulo": "Python Automation & Backend Contractor",
        "empresa": "AsyncLabs",
        "origem": "Internacional (USD/EUR)",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "matches_stack": ["python", "fastapi", "playwright", "docker", "postgresql"],
        "descricao": (
            "Async-first flexible hours contractor role building REST APIs with Python, "
            "FastAPI, Playwright, PostgreSQL, Docker and CI/CD."
        ),
    }

    res = evaluate_application_committee(
        _base_profile(),
        job,
        resume_markdown=_strong_xyz_resume(),
    )

    assert len(res["avaliacoes"]) == 7
    assert res["veredito"] == "APROVADO"
    assert res["aprovado"] is True
    assert res["media_geral"] >= 8.0
    assert res["veto"]["ativo"] is False
    assert res["compatibilidade_horario"]["status"] == "COMPATIVEL"


def test_committee_veto_by_ats_on_hostile_html_sparse_resume():
    job = {
        "titulo": "Backend Engineer",
        "empresa": "RemoteCo",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "descricao": "Async-first Python, FastAPI, Docker, PostgreSQL, Kubernetes and Redis.",
    }
    weak_html_resume = "<table><tr><td>Pedro</td><td>Dev Python com experiência geral.</td></tr></table>"

    res = evaluate_application_committee(
        _base_profile(),
        job,
        resume_markdown=weak_html_resume,
    )

    assert res["veredito"] == "VETADO"
    assert "ats_screener" in res["veto"]["personas_vetadoras"]
    assert res["plano_acao_prioritario"]


def test_committee_veto_by_skeptic_on_cliches_or_schedule_conflict():
    async_job = {
        "titulo": "Python Contractor",
        "empresa": "AsyncCo",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "descricao": "Async-first flexible hours Python Docker FastAPI SQL.",
    }
    cliche_resume = _strong_xyz_resume() + (
        "\n\nSou um profissional proativo, dinâmico, ninja, rockstar e workaholic "
        "que pensa fora da caixa e busca sinergia."
    )
    res_cliche = evaluate_application_committee(
        _base_profile(),
        async_job,
        resume_markdown=cliche_resume,
    )
    assert res_cliche["veredito"] == "VETADO"
    assert "skeptic_recruiter" in res_cliche["veto"]["personas_vetadoras"]

    # Conflito de rotina diurna / presencial também dispara veto do Recrutador Cético
    strict_day_job = {
        "titulo": "Python Developer",
        "empresa": "StrictCorp",
        "localizacao": "USA",
        "tipo_contrato": "Full-Time",
        "descricao": "Mandatory 9-5 core hours, daily standup at 10am and on-site presence.",
    }
    res_schedule = evaluate_application_committee(
        _base_profile(),
        strict_day_job,
        resume_markdown=_strong_xyz_resume(),
    )
    assert res_schedule["veredito"] == "VETADO"
    assert "skeptic_recruiter" in res_schedule["veto"]["personas_vetadoras"]


def test_committee_review_verdict_and_auto_calibration_without_markdown():
    job = {
        "titulo": "Python Backend Developer",
        "empresa": "CalmTech",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "descricao": "Async-first flexible hours Python, FastAPI, Docker, SQL.",
    }
    unquantified_resume = """# Pedro Teste
**Python Developer**
São Paulo, BR • pedro.teste@example.com

## Resumo Profissional
Desenvolvedor com atuação em Python, FastAPI, Docker e SQL em ambiente remoto e assíncrono.

## Competências Técnicas
- Python, FastAPI, Docker, SQL

## Experiência Profissional
### Backend Developer — CloudOps Corp
- Trabalhou na manutenção de endpoints Python e consultas SQL diárias.
- Auxiliou em rotinas operacionais com Docker.
"""

    res = evaluate_application_committee(
        _base_profile(),
        job,
        resume_markdown=unquantified_resume,
    )
    assert res["veto"]["ativo"] is False
    assert res["veredito"] == "REVISAR"
    assert res["media_geral"] < 8.0
    assert any("Product Manager" in item for item in res["plano_acao_prioritario"])

    # Sem passar resume_markdown -> auto-calibra internamente
    auto_res = evaluate_application_committee(_base_profile(), job)
    assert len(auto_res["avaliacoes"]) == 7
    assert auto_res["vaga_alvo"] == "Python Backend Developer (CalmTech)"


def test_committee_pluggable_llm_provider_and_prompt():
    profile_dict = _base_profile()
    job = {
        "titulo": "Senior Python Engineer",
        "empresa": "GlobalAsync",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "descricao": "Async-first Python and Docker.",
    }
    captured_prompt: list[str] = []

    def fake_llm_provider(prompt: str, schema_cls: type[CommitteePersonaBatch]) -> CommitteePersonaBatch:
        captured_prompt.append(prompt)
        assert schema_cls is CommitteePersonaBatch
        return CommitteePersonaBatch(
            avaliacoes=_make_batch(
                {
                    "ats_screener": 6.5,  # deve disparar veto mesmo com média >= 8.0
                    "tech_recruiter": 9.2,
                    "engineering_manager": 9.0,
                    "senior_peer": 9.1,
                    "product_manager": 8.9,
                    "cto_head": 9.0,
                    "skeptic_recruiter": 8.8,
                }
            )
        )

    res = evaluate_application_committee(
        profile_dict,
        job,
        resume_markdown=_strong_xyz_resume(),
        llm_provider=fake_llm_provider,
    )

    assert len(captured_prompt) == 1
    for expected in ("ATS Screener", "Recrutador Cético", "19:00 - 00:00", "Pedro Teste"):
        assert expected in captured_prompt[0]

    assert res["modo_avaliacao"] == "llm_estruturado"
    assert res["media_geral"] >= 8.0
    assert res["veredito"] == "VETADO"
    assert res["veto"]["personas_vetadoras"] == ["ats_screener"]
    assert build_committee_prompt(
        "CV",
        job,
        CandidateProfile.model_validate(profile_dict),
        _make_schedule_fit(),
    )
