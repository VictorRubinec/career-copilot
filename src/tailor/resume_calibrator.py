def calibrate_resume_for_job(profile_data, job_data):
    """
    Gera um currículo adaptado para a vaga alvo no formato Markdown limpo (ATS Friendly).
    """
    candidato = profile_data.get("candidato", {})
    competencias = profile_data.get("competencias", {})
    historico = profile_data.get("historico_profissional", [])
    schedule = profile_data.get("horario_trabalho_desejado", {})

    titulo_vaga = job_data.get("titulo", "Software Engineer")
    empresa = job_data.get("empresa", "Target Company")
    matches = job_data.get("matches_stack", [])

    # Resumo customizado com foco em entrega assíncrona
    resumo_customizado = (
        f"Engenheiro de Software e Automação com experiência prática em ecossistemas Python, rotinas de dados (ETL, SQL) "
        f"e integrações de APIs resilientes. Histórico comprovado na TIVIT construindo scripts de automação (Selenium/Playwright) "
        f"e ferramentas de diagnóstico operacional que reduzem falhas em produção. Perfil altamente autônomo e orientado a resultados, "
        f"comunicação técnica assíncrona fluida e disponibilidade alinhada para projetos internacionais (Contractor B2B) e regimes flexíveis."
    )

    # Reordena skills colocando as coincidentes primeiro
    skills_principais = competencias.get("principais", [])
    skills_ordenadas = sorted(
        skills_principais,
        key=lambda s: any(m in s.lower() for m in matches),
        reverse=True
    )

    linhas_experiencia = []
    for exp in historico:
        atividades = "\n".join([f"- {atv}" for atv in exp.get("atividades", [])])
        linhas_experiencia.append(f"""### {exp.get('cargo')} — {exp.get('empresa')}
*{exp.get('periodo')}*

{atividades}
""")

    curriculo_md = f"""# {candidato.get('nome')}
**{candidato.get('titulo_principal')}**  
{candidato.get('localizacao')} • {candidato.get('contato', {}).get('email')} • {candidato.get('contato', {}).get('telefone')}  
[LinkedIn]({candidato.get('contato', {}).get('linkedin')}) • [GitHub]({candidato.get('contato', {}).get('github')})

---

## Resumo Profissional
{resumo_customizado}

---

## Competências Técnicas
- **Linguagens & Frameworks Principais:** {', '.join(skills_ordenadas)}
- **Ferramentas & Infraestrutura:** {', '.join(competencias.get('secundarias', []))}
- **Idiomas:** Português (Nativo), Inglês (Comunicação Técnica & Assíncrona Fluente)

---

## Experiência Profissional
{"".join(linhas_experiencia)}

---

## Formação Acadêmica & Certificações
- **Bacharelado em Ciência da Computação**
- **Six Sigma White Belt** — Foco em Melhoria Contínua e Redução de Desperdícios Operacionais
"""

    return {
        "vaga_alvo": f"{titulo_vaga} ({empresa})",
        "curriculo_markdown": curriculo_md.strip()
    }
