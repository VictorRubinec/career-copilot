import re
from ..evaluators.schedule_matcher import evaluate_schedule_fit


def analyze_career_profile(profile_data):
    """
    Analisa o perfil do profissional, senioridade, histórico e viabilidade da rotina desejada.
    """
    candidato = profile_data.get("candidato", {})
    prefs = profile_data.get("preferencias_carreira", {})
    schedule = profile_data.get("horario_trabalho_desejado", {})
    competencias = profile_data.get("competencias", {})
    historico = profile_data.get("historico_profissional", [])

    # Análise de Tempo de Experiência e Nível Atual
    total_experiencias = len(historico)
    palavras_chave_historico = " ".join([
        f"{exp.get('cargo', '')} {' '.join(exp.get('atividades', []))}"
        for exp in historico
    ]).lower()

    # Cálculo preliminar de Senioridade Demonstrada
    if total_experiencias >= 4 or any(k in palavras_chave_historico for k in ["sênior", "senior", "lead", "arquiteto", "tech lead"]):
        senioridade_estimada = "Senior / Specialist"
        nivel_autonomia = "Alto (Capacidade de entrega ponta a ponta sem supervisão)"
    elif total_experiencias >= 2 or any(k in palavras_chave_historico for k in ["pleno", "mid-level", "analista"]):
        senioridade_estimada = "Pleno / Mid-Level"
        nivel_autonomia = "Médio-Alto (Autonomia em desenvolvimento e arquitetura de tarefas)"
    else:
        senioridade_estimada = "Júnior / Entry-Level"
        nivel_autonomia = "Operacional (Execução sólida de scripts, integrações e testes)"

    # Análise de Viabilidade da Rotina Noturna / Segundo Trabalho
    janela_seg_sex = schedule.get("janela_disponivel", {}).get("segunda_a_sexta", "19:00 - 00:00")
    carga_semanal = schedule.get("carga_semanal_horas", 20)
    permite_comercial = schedule.get("permite_reunioes_horario_comercial", False)

    viabilidade_noturna = {
        "status": "ALTA" if not permite_comercial and carga_semanal <= 25 else "MODERADA",
        "janela_declarada": janela_seg_sex,
        "carga_alvo": f"{carga_semanal}h semanais",
        "regime_recomendado": "Contractor B2B / Part-time Assíncrono",
        "pontos_atencao": (
            "Evitar empresas com cultura síncrona pesada (dailies às 10h/14h). "
            "Priorizar contratações baseadas em tickets no GitHub/Jira e comunicação assíncrona."
        )
    }

    # Avaliação de Stack de Destaque
    principais_skills = competencias.get("principais", [])
    secundarias_skills = competencias.get("secundarias", [])
    idiomas = competencias.get("idiomas", {})

    # Readiness Score para Mercado Internacional (0 a 100)
    readiness_intl = 40
    if "avancado" in idiomas.get("ingles", "").lower() or "intermediário-avançado" in idiomas.get("ingles", "").lower():
        readiness_intl += 30
    elif "técnico" in idiomas.get("ingles", "").lower():
        readiness_intl += 20

    if any(tech in ["Docker", "Git & GitHub Actions", "APIs REST (FastAPI, Requests)", "Python"] for tech in principais_skills):
        readiness_intl += 20

    if total_experiencias >= 1:
        readiness_intl += 10

    return {
        "candidato": {
            "nome": candidato.get("nome"),
            "titulo": candidato.get("titulo_principal"),
            "localizacao": candidato.get("localizacao")
        },
        "diagnostico_carreira": {
            "senioridade_estimada": senioridade_estimada,
            "senioridade_alvo": prefs.get("senioridade_alvo", []),
            "cargos_alvo": prefs.get("cargos_alvo", []),
            "nivel_autonomia": nivel_autonomia,
            "readiness_internacional_score": min(100, readiness_intl)
        },
        "analise_horario_trabalho": viabilidade_noturna,
        "competencias_chave": {
            "principais": principais_skills,
            "secundarias": secundarias_skills,
            "idiomas": idiomas
        },
        "proximos_passos_recomendados": [
            "Mineração de vagas ativas com filtros assíncronos e contractor B2B",
            "Geração de currículo customizado no formato Google XYZ",
            "Preparação de carta de apresentação (Cold Pitch) em inglês para recrutadores internacionais"
        ]
    }
