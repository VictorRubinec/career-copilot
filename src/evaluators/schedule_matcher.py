import re


ASYNC_POSITIVE_SIGNALS = [
    "async", "asynchronous", "flexible schedule", "flexible hours",
    "choose your own hours", "no core hours", "no meetings", "autonomy",
    "results-oriented", "result oriented", "contractor", "freelance",
    "part-time", "part time", "worldwide", "anywhere", "latam", "south america",
    "brazil", "b2b", "pj", "horário flexível", "horario flexivel", "assíncrono",
    "assincrono", "self-directed", "work whenever", "work from anywhere",
    "no mandatory hours", "own your schedule", "ticket-based"
]

SYNC_CONFLICT_SIGNALS = [
    "mandatory 9-5", "core hours 9am", "core hours 10am", "mandatory 9am-5pm",
    "strict schedule", "daily standup at 9am", "daily standup at 10am",
    "daily standup at 11am", "daily standup at 2pm", "live video required",
    "presencial", "híbrido", "hibrido", "on-site", "relocation required",
    "exclusividade integral", "dedicação exclusiva", "must overlap 8 hours",
    "core business hours required"
]


def evaluate_schedule_fit(job_text, job_location, job_type, candidate_schedule):
    """
    Avalia a compatibilidade entre a rotina/horário desejado do candidato e a vaga.
    
    candidate_schedule: dict com preferências horárias do perfil do usuário.
    Retorna:
      - score_horario (0 a 100)
      - status: 'COMPATIVEL' | 'PARCIALMENTE_COMPATIVEL' | 'INCOMPATIVEL'
      - justificativa: explicativo detalhado
      - red_flags: lista de potenciais colisões com horário diurno
      - sinais_positivos: termos assíncronos encontrados
    """
    text_lower = f"{job_text} {job_location} {job_type}".lower()

    # Preferências do candidato
    permite_comercial = candidate_schedule.get("permite_reunioes_horario_comercial", False)
    turnos_aceitos = candidate_schedule.get("turnos_aceitos", ["noturno", "flexivel_assincrono"])
    tipo_rotina = candidate_schedule.get("tipo_rotina", "Segundo Trabalho / Turno Noturno")

    sinais_positivos = [sig for sig in ASYNC_POSITIVE_SIGNALS if sig in text_lower]
    red_flags = [flag for flag in SYNC_CONFLICT_SIGNALS if flag in text_lower]

    # Pontuação base para trabalho 100% remoto
    score = 55

    # Bonificação por sinais de flexibilidade e autonomia
    score += min(35, len(sinais_positivos) * 7)

    # Bonificação por modalidade B2B / Contractor / Part-time
    if any(k in text_lower for k in ["contract", "contractor", "freelance", "part-time", "b2b", "pj"]):
        score += 10

    # Bonificação por abrangência geográfica irrestrita (Anywhere / Worldwide / LATAM)
    if any(k in job_location.lower() for k in ["worldwide", "anywhere", "latam", "americas", "global"]):
        score += 10

    # Penalização severa para red flags de horário fixo ou reuniões diárias obrigatórias
    if red_flags:
        score -= (len(red_flags) * 30)

    # Se a vaga exige presencial/híbrido
    if any(k in text_lower for k in ["presencial", "híbrido", "hibrido", "on-site"]):
        score = min(score, 10)

    score_final = max(0, min(100, score))

    if score_final >= 75 and not red_flags:
        status = "COMPATIVEL"
        justificativa = (
            f"Excelente compatibilidade com sua rotina de {tipo_rotina}. "
            "A vaga apresenta fortes indícios de cultura assíncrona, foco em entregas ou regime contractor/B2B sem exigência de presença contínua em horário comercial."
        )
    elif score_final >= 50:
        status = "PARCIALMENTE_COMPATIVEL"
        justificativa = (
            f"Compatibilidade moderada com sua rotina. Pode exigir alinhamento prévio sobre flexibilidade de turnos. "
            "Recomenda-se confirmar na entrevista se as cerimônias síncronas podem ocorrer fora do seu horário comercial diurno."
        )
    else:
        status = "INCOMPATIVEL"
        justificativa = (
            f"Alto risco de colisão de horários. Foram identificadas restrições rígidas de horário comercial diurno ou presença síncrona incompatível com {tipo_rotina}."
        )

    return {
        "score_horario": score_final,
        "status": status,
        "justificativa": justificativa,
        "red_flags": red_flags,
        "sinais_positivos": sinais_positivos,
        "janela_candidato": candidate_schedule.get("janela_disponivel", {}),
        "permite_reunioes_comercial": permite_comercial
    }
