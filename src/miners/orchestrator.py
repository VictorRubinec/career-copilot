import re
from .remotive import mine_remotive
from .jobicy import mine_jobicy
from .weworkremotely import mine_weworkremotely
from .github_br import mine_github_brasil
from ..evaluators.schedule_matcher import evaluate_schedule_fit


def calculate_stack_score(text, profile_skills):
    """Calcula aderência da stack do candidato (0 a 100)."""
    text_lower = text.lower()
    matches = []
    
    for skill in profile_skills:
        # Simplifica nomes complexos como "APIs REST (FastAPI, Requests)"
        terms = re.split(r'[\s,\(\)/]+', skill.lower())
        for term in terms:
            if len(term) >= 3 and re.search(r'\b' + re.escape(term) + r'\b', text_lower):
                matches.append(term)
                break

    unique_matches = list(set(matches))
    score = min(100, int((len(unique_matches) / 4.0) * 100))
    return score, unique_matches


def mine_all_opportunities(profile_data, modo="todos", min_schedule=50, min_stack=25):
    """
    Minera vagas em todas as fontes, cruza com a rotina horária e a stack do candidato.
    """
    candidate_schedule = profile_data.get("horario_trabalho_desejado", {})
    profile_skills = (
        profile_data.get("competencias", {}).get("principais", []) +
        profile_data.get("competencias", {}).get("secundarias", [])
    )

    brutas = []

    if modo in ["todos", "internacional"]:
        brutas.extend(mine_remotive())
        brutas.extend(mine_jobicy())
        brutas.extend(mine_weworkremotely())

    if modo in ["todos", "nacional"]:
        brutas.extend(mine_github_brasil())

    # Deduplicação por URL
    unicas = {}
    for v in brutas:
        if v.get("url") and v["url"] not in unicas:
            unicas[v["url"]] = v

    lista = list(unicas.values())
    qualificadas = []

    for v in lista:
        texto_analise = f"{v.get('titulo', '')} {v.get('descricao', '')} {v.get('resumo', '')}"
        
        # 1. Análise de Horário / Rotina
        schedule_res = evaluate_schedule_fit(
            texto_analise,
            v.get("localizacao", ""),
            v.get("tipo_contrato", ""),
            candidate_schedule
        )

        # 2. Análise de Stack
        stack_score, matches = calculate_stack_score(texto_analise, profile_skills)

        # 3. Score Composto (60% Horário/Rotina + 40% Stack)
        score_composto = round(0.6 * schedule_res["score_horario"] + 0.4 * stack_score, 1)

        v["schedule_fit"] = schedule_res
        v["stack_score"] = stack_score
        v["matches_stack"] = matches
        v["score_composto"] = score_composto

        if schedule_res["score_horario"] >= min_schedule and stack_score >= min_stack:
            qualificadas.append(v)

    qualificadas.sort(key=lambda x: x["score_composto"], reverse=True)
    return qualificadas
