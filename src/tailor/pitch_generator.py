"""Gerador dinâmico de cartas de apresentação (Cold Pitch) em inglês e português."""

from __future__ import annotations

from typing import Any

from ..models import CandidateProfile, CoverPitchBundle


def generate_cover_pitch(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Gera mensagens de abordagem (Cold Pitch) em Inglês e Português sem dados fixos.
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    candidato = profile.candidato
    contato = candidato.contato
    historico = profile.historico_profissional
    competencias = profile.competencias

    titulo_vaga = str(job_data.get("titulo", "Software Engineer"))
    empresa = str(job_data.get("empresa", "Hiring Team"))
    matches = [str(m) for m in job_data.get("matches_stack", [])]

    skills_destaque = (
        ", ".join(matches[:4])
        if matches
        else ", ".join(competencias.principais[:4]) or "backend & automation engineering"
    )

    exp_context_en = (
        f"most recently as {historico[0].cargo} at {historico[0].empresa}, delivering production systems, automated workflows, and reliable integrations"
        if historico
        else "designing reliable automation workflows, APIs, and production integrations"
    )
    exp_context_pt = (
        f"Em minha atuação mais recente na {historico[0].empresa} ({historico[0].cargo}), construí automações, rotinas de dados e integrações resilientes focadas em produção."
        if historico
        else "Tenho experiência prática construindo automações, integrações via APIs REST e pipelines orientados a confiabilidade."
    )

    linkedin_ref = (
        f" You can also explore my background on LinkedIn ({contato.linkedin})."
        if contato.linkedin
        else ""
    )
    contato_footer_pt = " | ".join(
        part for part in (contato.telefone, contato.email) if part
    )

    pitch_ingles = f"""Subject: Application: {titulo_vaga} — {candidato.nome}

Hi {empresa} Team,

I came across your opening for {titulo_vaga} and wanted to reach out directly.

With hands-on expertise in {skills_destaque}, I bring practical experience {exp_context_en}.

I thrive in autonomous, async-first environments where execution is driven by clear documentation, tickets, and pull requests. Given your distributed setup, my working style aligns seamlessly with your engineering cadence.

I would love to learn more about the challenges your team is tackling. My resume is attached.{linkedin_ref}

Best regards,
{candidato.nome}
{contato.email}"""

    pitch_portugues = f"""Assunto: Candidatura: {titulo_vaga} — {candidato.nome}

Olá, equipe da {empresa},

Gostaria de apresentar minha candidatura para a posição de {titulo_vaga}.

Tenho sólida experiência em {skills_destaque}. {exp_context_pt}

Opero com alta autonomia e comunicação assíncrona clara (tickets, Slack, Notion e PRs no GitHub), com foco constante em previsibilidade técnica e entrega de valor.

Fico à disposição para conversarmos sobre como posso contribuir com o time.

Atenciosamente,
{candidato.nome}
{contato_footer_pt}"""

    bundle = CoverPitchBundle(
        vaga=f"{titulo_vaga} @ {empresa}",
        pitch_ingles=pitch_ingles.strip(),
        pitch_portugues=pitch_portugues.strip(),
    )
    return bundle.model_dump()
