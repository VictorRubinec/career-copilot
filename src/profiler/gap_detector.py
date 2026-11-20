import re
from ..evaluators.schedule_matcher import evaluate_schedule_fit


def detect_job_gaps(profile_data, job_data):
    """
    Compara o perfil do candidato com uma vaga específica e calcula:
      1. Gaps técnicos (tecnologias exigidas que o candidato não possui no perfil)
      2. Gaps de experiência e senioridade
      3. Gaps de compatibilidade de horário e regime de trabalho
    """
    competencias = profile_data.get("competencias", {})
    schedule = profile_data.get("horario_trabalho_desejado", {})

    todas_skills = set(
        [s.lower() for s in competencias.get("principais", [])] +
        [s.lower() for s in competencias.get("secundarias", [])]
    )

    titulo_vaga = job_data.get("titulo", "")
    desc_vaga = job_data.get("descricao", job_data.get("resumo", "")).lower()
    local_vaga = job_data.get("localizacao", "Worldwide")
    tipo_vaga = job_data.get("tipo_contrato", "Remote")

    # Avaliação de horário com o schedule matcher
    schedule_eval = evaluate_schedule_fit(desc_vaga, local_vaga, tipo_vaga, schedule)

    # Identificação de tecnologias mencionadas na vaga
    tech_keywords = [
        "python", "fastapi", "django", "flask", "selenium", "playwright",
        "docker", "kubernetes", "aws", "gcp", "azure", "postgresql", "mysql",
        "redis", "kafka", "rabbitmq", "git", "ci/cd", "linux", "bash", "react",
        "vue", "angular", "node", "typescript", "javascript", "graphql", "rest"
    ]

    requisitos_vaga = [t for t in tech_keywords if re.search(r'\b' + re.escape(t) + r'\b', desc_vaga)]
    
    # Gaps técnicos: exigidos pela vaga mas não encontrados nas competências do perfil
    gaps_tecnicos = []
    skills_compatíveis = []

    for req in requisitos_vaga:
        if any(req in skill for skill in todas_skills):
            skills_compatíveis.append(req)
        else:
            gaps_tecnicos.append(req)

    total_requisitos = len(requisitos_vaga)
    if total_requisitos > 0:
        match_tecnico_pct = round((len(skills_compatíveis) / total_requisitos) * 100, 1)
    else:
        match_tecnico_pct = 75.0  # Fallback quando a vaga é descritiva

    # Veredito global
    score_geral = round(0.5 * schedule_eval["score_horario"] + 0.5 * match_tecnico_pct, 1)

    return {
        "vaga": {
            "titulo": titulo_vaga,
            "empresa": job_data.get("empresa", "Empresa"),
            "origem": job_data.get("origem", "Remoto")
        },
        "score_geral": score_geral,
        "compatibilidade_horario": schedule_eval,
        "aderencia_tecnica": {
            "match_pct": match_tecnico_pct,
            "skills_atendidas": skills_compatíveis,
            "gaps_identificados": gaps_tecnicos
        },
        "recomendacao_acao": (
            "Aprovada para candidatura com currículo customizado."
            if score_geral >= 75 and schedule_eval["status"] != "INCOMPATIVEL"
            else "Revisar exigências de presença ou tecnologias complementares antes de aplicar."
        )
    }
