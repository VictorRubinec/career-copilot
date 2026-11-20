"""Motor de avaliação de compatibilidade de horário, fuso e cultura assíncrona."""

from __future__ import annotations

import re
from typing import Any

from ..models import (
    SCHEDULE_STATUS_LABELS,
    DesiredSchedule,
    ScheduleFitResult,
    ScheduleStatus,
)

# Sinais positivos de trabalho assíncrono / flexível / contractor (contextuais)
_POSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("async-first", re.compile(r"\basync[-\s]?first\b", re.IGNORECASE)),
    (
        "asynchronous work/culture",
        re.compile(
            r"\basynchronous(?:ly)?\s+(?:work|working|culture|communication|team|collaboration|environment|workflow|first)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "work asynchronously",
        re.compile(r"\b(?:work|communicate|operate|collaborate)\s+asynchronously\b", re.IGNORECASE),
    ),
    ("cultura assíncrona", re.compile(r"\b(?:cultura|trabalho|comunica[cç][aã]o)\s+ass[ií]ncron[ao]\b", re.IGNORECASE)),
    ("flexible schedule/hours", re.compile(r"\bflexible\s+(?:work(?:ing)?\s+)?(?:schedule|hours)\b", re.IGNORECASE)),
    ("horário flexível", re.compile(r"\bhor[aá]rio\s+flex[ií]vel\b", re.IGNORECASE)),
    ("choose your own hours", re.compile(r"\b(?:choose|set|own)\s+your\s+(?:own\s+)?(?:hours|schedule)\b", re.IGNORECASE)),
    (
        "no core/mandatory hours",
        re.compile(r"\bno\s+(?:core|mandatory|fixed)\s+(?:working\s+)?hours\b", re.IGNORECASE),
    ),
    ("no meetings", re.compile(r"\bno\s+(?:daily\s+)?(?:meetings|stand[-\s]?ups?)\b", re.IGNORECASE)),
    ("results-oriented", re.compile(r"\bresults?[-\s]oriented\b|\boutcome[-\s]driven\b", re.IGNORECASE)),
    ("self-directed", re.compile(r"\bself[-\s]directed\b", re.IGNORECASE)),
    ("autonomy", re.compile(r"\bautonomy\b", re.IGNORECASE)),
    ("work whenever", re.compile(r"\bwork\s+whenever\b", re.IGNORECASE)),
    ("work from anywhere", re.compile(r"\bwork\s+from\s+anywhere\b", re.IGNORECASE)),
    ("ticket-based", re.compile(r"\bticket[-\s]based\b", re.IGNORECASE)),
    ("contractor", re.compile(r"\bcontractors?\b", re.IGNORECASE)),
    ("freelance", re.compile(r"\bfreelance(?:r)?\b", re.IGNORECASE)),
    (
        "part-time",
        re.compile(r"(?<!return\s)(?<!returning\s)\bpart[-\s]?time\b", re.IGNORECASE),
    ),
    (
        "b2b contract",
        re.compile(r"\b(?:b2b\s+contract|contract\s+b2b|contractor\s+b2b|regime\s+b2b)\b", re.IGNORECASE),
    ),
    ("pj", re.compile(r"\b(?:regime\s+pj|contrata[cç][aã]o\s+pj|pj)\b", re.IGNORECASE)),
    ("worldwide/anywhere", re.compile(r"\b(?:worldwide|work\s+anywhere|anywhere\s+in\s+the\s+world)\b", re.IGNORECASE)),
    ("latam/brazil", re.compile(r"\b(?:latam|latin\s+america|south\s+america|brazil|brasil)\b", re.IGNORECASE)),
)

# Sinais de veto presencial / híbrido / realocação
_ONSITE_RELOCATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "presencial/on-site",
        re.compile(
            r"(?<!no\s)(?<!not\s)(?<!non-)\b(?:presencial|on[-\s]?site|in[-\s]?person)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "relocation required",
        re.compile(
            r"\b(?:relocation\s+required|willing(?:ness)?\s+to\s+relocate|willing\s+to\s+relocate|"
            r"must\s+relocate|ability\s+(?:and\s+willingness\s+)?to\s+relocate)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "híbrido/hybrid",
        re.compile(
            r"\b(?:h[ií]brido|hybrid\s+(?:role|position|work|schedule|model|required|only|office))\b",
            re.IGNORECASE,
        ),
    ),
)

# Sinais de conflito com janela diurna (09h-18h BRT) / microgerenciamento síncrono
_SYNC_CONFLICT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mandatory 9-5", re.compile(r"\bmandatory\s+9(?:am)?\s*[-–to]+\s*5(?:pm)?\b", re.IGNORECASE)),
    (
        "core business hours",
        re.compile(
            r"\b(?:core\s+(?:business\s+)?hours\s+(?:required|mandatory|9am|10am|8am|from\s+\d+)|"
            r"core\s+hours\s+(?:8|9|10)\s*am)\b",
            re.IGNORECASE,
        ),
    ),
    ("strict schedule", re.compile(r"\bstrict\s+schedule\b", re.IGNORECASE)),
    (
        "daily standup at daytime",
        re.compile(
            r"\bdaily\s+(?:stand[-\s]?up|scrum|sync)\s+at\s+(?:8|9|10|11|12|1|2|3|4|5)\s*(?:am|pm|h)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "mandatory daily standup/sync",
        re.compile(
            r"\b(?:mandatory|required)\s+(?:daily\s+)?(?:stand[-\s]?ups?|sync\s+meetings?|business\s+hours)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "horário comercial obrigatório",
        re.compile(
            r"\bhor[aá]rio\s+comercial\s+(?:obrigat[oó]rio|fixo|integral)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "live video/camera/tracking",
        re.compile(
            r"\b(?:live\s+video\s+required|cameras?\s+(?:always\s+)?on|"
            r"screen\s+monitoring|time\s+tracker\s+required)\b",
            re.IGNORECASE,
        ),
    ),
    ("exclusividade integral", re.compile(r"\b(?:exclusividade\s+integral|dedica[cç][aã]o\s+exclusiva)\b", re.IGNORECASE)),
    (
        "heavy daytime overlap",
        re.compile(
            r"\b(?:must\s+overlap|overlap\s+(?:of\s+)?at\s+least)\s+(?:[4-9]|1[0-2])\s*(?:\+\s*)?hours\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fixed timezone business hours",
        re.compile(
            r"\b(?:est|edt|pst|pdt|cst|cdt|mst|cet|gmt|brt)\s+"
            r"(?:business|working|core)\s+hours\s+(?:required|mandatory|only)\b",
            re.IGNORECASE,
        ),
    ),
)

_REMOTE_OR_HYBRID_RE = re.compile(
    r"\b(?:remote\s+(?:or|and|/)\s+hybrid|hybrid\s+(?:or|and|/)\s+remote)\b",
    re.IGNORECASE,
)


def evaluate_schedule_fit(
    job_text: str,
    job_location: str,
    job_type: str,
    candidate_schedule: dict[str, Any] | DesiredSchedule,
) -> dict[str, Any]:
    """
    Avalia a compatibilidade entre a rotina/horário desejado do candidato e a vaga.

    Aplica proteção estrita contra falsos positivos técnicos e colisão com o turno
    comercial diurno (09h-18h BRT).
    """
    schedule = (
        candidate_schedule
        if isinstance(candidate_schedule, DesiredSchedule)
        else DesiredSchedule.model_validate(candidate_schedule or {})
    )

    full_text = f"{job_text or ''} {job_location or ''} {job_type or ''}"
    location_lower = (job_location or "").lower()
    contract_lower = (job_type or "").lower()

    permite_comercial = schedule.permite_reunioes_horario_comercial
    tipo_rotina = schedule.tipo_rotina

    sinais_positivos = [
        label for label, pattern in _POSITIVE_PATTERNS if pattern.search(full_text)
    ]

    onsite_flags: list[str] = []
    for label, pattern in _ONSITE_RELOCATION_PATTERNS:
        if label == "híbrido/hybrid" and _REMOTE_OR_HYBRID_RE.search(full_text):
            continue
        if pattern.search(full_text):
            onsite_flags.append(label)

    sync_flags = [
        label for label, pattern in _SYNC_CONFLICT_PATTERNS if pattern.search(full_text)
    ]
    red_flags = onsite_flags + sync_flags

    # Pontuação base para trabalho remoto
    score = 55

    # Bonificação por sinais de flexibilidade e autonomia (teto +35)
    score += min(35, len(sinais_positivos) * 7)

    # Bonificação por regime B2B / Contractor / Part-time explícito no contrato ou texto
    if any(
        k in contract_lower
        for k in ("contract", "contractor", "freelance", "part-time", "part time", "b2b", "pj")
    ) or any(sig in sinais_positivos for sig in ("contractor", "freelance", "part-time", "b2b contract", "pj")):
        score += 10

    # Bonificação por abrangência geográfica irrestrita ou LATAM/Brasil
    if any(
        k in location_lower
        for k in ("worldwide", "anywhere", "latam", "latin america", "south america", "americas", "global", "brazil", "brasil")
    ):
        score += 10

    # Penalização por conflitos síncronos considerando tolerância a horário comercial
    if sync_flags:
        penalty_per_flag = 15 if permite_comercial else 35
        score -= len(sync_flags) * penalty_per_flag
        if not permite_comercial:
            score = min(score, 45)

    # Veto absoluto para presencial, híbrido exclusivo ou necessidade de realocação
    if onsite_flags:
        score = min(score, 10)

    score_final = max(0, min(100, score))

    status: ScheduleStatus
    if score_final >= 75 and not red_flags:
        status = "COMPATIVEL"
        justificativa = (
            f"Excelente compatibilidade com sua rotina de {tipo_rotina}. "
            "A vaga apresenta indícios consistentes de cultura assíncrona, foco em entregas ou regime contractor/B2B sem exigência de presença em horário comercial."
        )
    elif score_final >= 50 and not onsite_flags:
        status = "PARCIALMENTE_COMPATIVEL"
        justificativa = (
            "Compatibilidade moderada com sua rotina. Pode exigir alinhamento prévio sobre flexibilidade de turnos. "
            "Confirme na triagem se eventuais cerimônias síncronas cabem fora do horário comercial diurno."
        )
    else:
        status = "INCOMPATIVEL"
        justificativa = (
            f"Alto risco de colisão de horários ou regime incompatível com {tipo_rotina}. "
            f"Sinais críticos detectados: {', '.join(red_flags) if red_flags else 'baixa evidência de flexibilidade'}."
        )

    result = ScheduleFitResult(
        score_horario=score_final,
        status=status,
        classificacao_exibicao=SCHEDULE_STATUS_LABELS[status],
        justificativa=justificativa,
        red_flags=red_flags,
        sinais_positivos=sinais_positivos,
        janela_candidato=schedule.janela_disponivel,
        permite_reunioes_comercial=permite_comercial,
    )
    return result.model_dump()
