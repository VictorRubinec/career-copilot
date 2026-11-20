"""Detector de gaps técnicos e de horário comparando perfil e vaga."""

from __future__ import annotations

import re
from typing import Any

from ..evaluators.schedule_matcher import evaluate_schedule_fit
from ..models import (
    CandidateProfile,
    JobGapReport,
    JobSummary,
    ScheduleFitResult,
    TechnicalFitSummary,
)

TECH_KEYWORDS: tuple[str, ...] = (
    "python",
    "fastapi",
    "django",
    "flask",
    "selenium",
    "playwright",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "postgresql",
    "mysql",
    "sql",
    "etl",
    "scraping",
    "redis",
    "kafka",
    "rabbitmq",
    "git",
    "github actions",
    "ci/cd",
    "terraform",
    "linux",
    "bash",
    "shell",
    "react",
    "vue",
    "angular",
    "node",
    "typescript",
    "javascript",
    "graphql",
    "rest",
    "java",
    "spring",
    "pytest",
    "qa",
    "celery",
    "pandas",
    "golang",
)


def detect_job_gaps(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Compara o perfil do candidato com uma vaga específica e calcula aderência de
    horário, stack técnica e recomendação de candidatura.
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    todas_skills = {
        *(s.lower() for s in profile.competencias.principais),
        *(s.lower() for s in profile.competencias.secundarias),
    }

    titulo_vaga = str(job_data.get("titulo", ""))
    desc_vaga = str(job_data.get("descricao", job_data.get("resumo", ""))).lower()
    local_vaga = str(job_data.get("localizacao", "Worldwide"))
    tipo_vaga = str(job_data.get("tipo_contrato", "Remote"))

    schedule_eval_dict = evaluate_schedule_fit(
        f"{titulo_vaga} {desc_vaga}",
        local_vaga,
        tipo_vaga,
        profile.horario_trabalho_desejado,
    )
    schedule_eval = ScheduleFitResult.model_validate(schedule_eval_dict)

    requisitos_vaga = [
        tech
        for tech in TECH_KEYWORDS
        if re.search(r"\b" + re.escape(tech) + r"\b", desc_vaga)
    ]

    gaps_tecnicos: list[str] = []
    skills_compativeis: list[str] = []

    for req in requisitos_vaga:
        if any(req in skill for skill in todas_skills):
            skills_compativeis.append(req)
        else:
            gaps_tecnicos.append(req)

    total_requisitos = len(requisitos_vaga)
    if total_requisitos > 0:
        match_tecnico_pct = round((len(skills_compativeis) / total_requisitos) * 100, 1)
    else:
        match_tecnico_pct = 75.0

    score_geral = round(0.5 * schedule_eval.score_horario + 0.5 * match_tecnico_pct, 1)

    recomendacao = (
        "Aprovada para candidatura com currículo customizado."
        if score_geral >= 75 and schedule_eval.status != "INCOMPATIVEL"
        else "Revisar exigências de presença ou tecnologias complementares antes de aplicar."
    )

    report = JobGapReport(
        vaga=JobSummary(
            titulo=titulo_vaga,
            empresa=str(job_data.get("empresa", "Empresa")),
            origem=str(job_data.get("origem", "Remoto")),
        ),
        score_geral=score_geral,
        compatibilidade_horario=schedule_eval,
        aderencia_tecnica=TechnicalFitSummary(
            match_pct=match_tecnico_pct,
            skills_atendidas=skills_compativeis,
            gaps_identificados=gaps_tecnicos,
        ),
        recomendacao_acao=recomendacao,
    )
    return report.model_dump()
