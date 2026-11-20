"""Analisador de perfil profissional, senioridade e viabilidade de turno noturno."""

from __future__ import annotations

from typing import Any

from ..models import (
    CandidateProfile,
    CandidateSummary,
    CareerDiagnosis,
    CareerDiagnosticDetails,
    ScheduleViability,
)


def analyze_career_profile(profile_data: dict[str, Any] | CandidateProfile) -> dict[str, Any]:
    """
    Analisa o perfil do profissional, senioridade, histórico e viabilidade da rotina desejada.
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    candidato = profile.candidato
    prefs = profile.preferencias_carreira
    schedule = profile.horario_trabalho_desejado
    competencias = profile.competencias
    historico = profile.historico_profissional

    total_experiencias = len(historico)
    non_intern_experiences = [
        exp
        for exp in historico
        if not any(tag in exp.cargo.lower() for tag in ("estagi", "intern", "trainee"))
    ]
    palavras_chave_historico = " ".join(
        f"{exp.cargo} {' '.join(exp.atividades)}" for exp in historico
    ).lower()

    if total_experiencias >= 4 or any(
        k in palavras_chave_historico
        for k in ("sênior", "senior", "staff", "principal", "arquiteto", "tech lead", "lead engineer")
    ):
        senioridade_estimada = "Senior / Specialist"
        nivel_autonomia = "Alto (Capacidade de entrega ponta a ponta sem supervisão)"
    elif len(non_intern_experiences) >= 2 or (
        total_experiencias >= 2
        and any(k in palavras_chave_historico for k in ("pleno", "mid-level", "analista", "engineer"))
    ):
        senioridade_estimada = "Pleno / Mid-Level"
        nivel_autonomia = "Médio-Alto (Autonomia em desenvolvimento e arquitetura de tarefas)"
    else:
        senioridade_estimada = "Júnior / Entry-Level"
        nivel_autonomia = "Operacional (Execução sólida de scripts, integrações e testes)"

    janela_seg_sex = schedule.janela_disponivel.get("segunda_a_sexta", "19:00 - 00:00")
    carga_semanal = schedule.carga_semanal_horas
    permite_comercial = schedule.permite_reunioes_horario_comercial

    viabilidade_noturna = ScheduleViability(
        status="ALTA" if not permite_comercial and carga_semanal <= 25 else "MODERADA",
        janela_declarada=janela_seg_sex,
        carga_alvo=f"{carga_semanal}h semanais",
        regime_recomendado="Contractor B2B / Part-time Assíncrono",
        pontos_atencao=(
            "Evitar empresas com cultura síncrona pesada (dailies às 10h/14h). "
            "Priorizar contratações baseadas em tickets no GitHub/Jira e comunicação assíncrona."
        ),
    )

    idiomas = competencias.idiomas
    ingles_desc = idiomas.get("ingles", "").lower()

    readiness_intl = 40
    if any(
        lvl in ingles_desc
        for lvl in ("fluente", "fluent", "avançado", "avancado", "intermediário-avançado", "c1", "c2", "b2")
    ):
        readiness_intl += 30
    elif any(lvl in ingles_desc for lvl in ("técnico", "tecnico", "intermediário", "intermediario", "b1")):
        readiness_intl += 20

    skills_lower = " ".join(competencias.principais).lower()
    if any(tech in skills_lower for tech in ("docker", "github", "fastapi", "python", "rest", "sql")):
        readiness_intl += 20

    if total_experiencias >= 1:
        readiness_intl += 10

    diagnosis = CareerDiagnosis(
        candidato=CandidateSummary(
            nome=candidato.nome,
            titulo=candidato.titulo_principal,
            localizacao=candidato.localizacao,
        ),
        diagnostico_carreira=CareerDiagnosticDetails(
            senioridade_estimada=senioridade_estimada,
            senioridade_alvo=prefs.senioridade_alvo,
            cargos_alvo=prefs.cargos_alvo,
            nivel_autonomia=nivel_autonomia,
            readiness_internacional_score=min(100, readiness_intl),
        ),
        analise_horario_trabalho=viabilidade_noturna,
        competencias_chave=competencias,
        proximos_passos_recomendados=[
            "Mineração de vagas ativas com filtros assíncronos e contractor B2B",
            "Geração de currículo customizado no formato Google XYZ",
            "Preparação de carta de apresentação (Cold Pitch) em inglês para recrutadores internacionais",
        ],
    )
    return diagnosis.model_dump()
