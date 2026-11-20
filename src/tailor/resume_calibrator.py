"""Calibrador dinâmico de currículos ATS-friendly orientados a entregas."""

from __future__ import annotations

from typing import Any

from ..models import CandidateProfile, TailoredResume


def _build_contact_links(profile: CandidateProfile) -> str:
    contato = profile.candidato.contato
    links: list[str] = []
    if contato.linkedin:
        links.append(f"[LinkedIn]({contato.linkedin})")
    if contato.github:
        links.append(f"[GitHub]({contato.github})")
    if contato.portfolio:
        links.append(f"[Portfolio]({contato.portfolio})")
    return " • ".join(links)


def _build_contact_line(profile: CandidateProfile) -> str:
    parts = [
        part
        for part in (
            profile.candidato.localizacao,
            profile.candidato.contato.email,
            profile.candidato.contato.telefone,
        )
        if part
    ]
    return " • ".join(parts)


def calibrate_resume_for_job(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Gera um currículo adaptado para a vaga alvo no formato Markdown limpo (ATS Friendly),
    preenchido 100% dinamicamente a partir do perfil do candidato.
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    candidato = profile.candidato
    competencias = profile.competencias
    historico = profile.historico_profissional
    schedule = profile.horario_trabalho_desejado
    prefs = profile.preferencias_carreira

    titulo_vaga = str(job_data.get("titulo", "Software Engineer"))
    empresa = str(job_data.get("empresa", "Target Company"))
    matches = [str(m).lower() for m in job_data.get("matches_stack", [])]

    skills_principais = competencias.principais
    skills_ordenadas = sorted(
        skills_principais,
        key=lambda s: any(m in s.lower() for m in matches),
        reverse=True,
    )

    top_skills_texto = ", ".join(skills_ordenadas[:4]) if skills_ordenadas else "engenharia de software"
    experiencia_destaque = (
        f"Experiência prévia na {historico[0].empresa} como {historico[0].cargo}"
        if historico
        else "Experiência prática em entregas técnicas orientadas a impacto"
    )
    regimes_texto = (
        ", ".join(prefs.regimes_contratuais[:2])
        if prefs.regimes_contratuais
        else "Contractor B2B e regimes flexíveis"
    )
    janela_texto = schedule.janela_disponivel.get("segunda_a_sexta", "horário flexível")

    resumo_customizado = (
        f"{candidato.titulo_principal or 'Engenheiro de Software'} com foco em {top_skills_texto}, "
        f"alinhado aos requisitos da posição de {titulo_vaga} na {empresa}. "
        f"{experiencia_destaque}, com atuação voltada à confiabilidade, automação e redução de gargalos operacionais. "
        f"Perfil autônomo orientado a entregas, comunicação técnica assíncrona clara e disponibilidade para atuação em {regimes_texto} ({janela_texto})."
    )

    linhas_experiencia: list[str] = []
    for exp in historico:
        atividades = "\n".join(f"- {atv}" for atv in exp.atividades)
        periodo_line = f"*{exp.periodo}*\n\n" if exp.periodo else "\n"
        linhas_experiencia.append(
            f"### {exp.cargo} — {exp.empresa}\n{periodo_line}{atividades}\n"
        )

    idiomas_items = [
        f"{idioma.capitalize()} ({nivel})" for idioma, nivel in competencias.idiomas.items()
    ]
    idiomas_texto = ", ".join(idiomas_items) if idiomas_items else "Não especificado"

    secoes_tecnicas = [f"- **Linguagens & Frameworks Principais:** {', '.join(skills_ordenadas)}"]
    if competencias.secundarias:
        secoes_tecnicas.append(
            f"- **Ferramentas & Infraestrutura:** {', '.join(competencias.secundarias)}"
        )
    secoes_tecnicas.append(f"- **Idiomas:** {idiomas_texto}")

    cabecalho_linhas = [f"# {candidato.nome}"]
    if candidato.titulo_principal:
        cabecalho_linhas.append(f"**{candidato.titulo_principal}**  ")
    contact_line = _build_contact_line(profile)
    if contact_line:
        cabecalho_linhas.append(f"{contact_line}  ")
    links_line = _build_contact_links(profile)
    if links_line:
        cabecalho_linhas.append(links_line)

    secoes = [
        "\n".join(cabecalho_linhas),
        "---",
        f"## Resumo Profissional\n{resumo_customizado}",
        "---",
        "## Competências Técnicas\n" + "\n".join(secoes_tecnicas),
    ]

    if linhas_experiencia:
        secoes.extend(["---", "## Experiência Profissional\n" + "\n".join(linhas_experiencia).strip()])

    if profile.formacao_e_certificacoes:
        itens_formacao = []
        for item in profile.formacao_e_certificacoes:
            if item.detalhe:
                itens_formacao.append(f"- **{item.titulo}** — {item.detalhe}")
            else:
                itens_formacao.append(f"- **{item.titulo}**")
        secoes.extend(["---", "## Formação Acadêmica & Certificações\n" + "\n".join(itens_formacao)])

    curriculo_md = "\n\n".join(secoes)
    result = TailoredResume(
        vaga_alvo=f"{titulo_vaga} ({empresa})",
        curriculo_markdown=curriculo_md.strip(),
    )
    return result.model_dump()
