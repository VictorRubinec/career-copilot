"""Orquestrador concorrente de mineração, ranqueamento de stack e deduplicação."""

from __future__ import annotations

import inspect
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ..config import get_logger
from ..evaluators.schedule_matcher import evaluate_schedule_fit
from ..models import CandidateProfile, QualifiedJobOpportunity
from .ashby import mine_ashby
from .github_br import mine_github_brasil
from .greenhouse import mine_greenhouse
from .hackernews import mine_hackernews
from .jobicy import mine_jobicy
from .lever import mine_lever
from .remotive import mine_remotive
from .weworkremotely import mine_weworkremotely

logger = get_logger(__name__)

SHORT_TECH_SKILLS: frozenset[str] = frozenset(
    {"qa", "go", "ci", "cd", "js", "ts", "ai", "ml", "r"}
)

INTERNATIONAL_SOURCES: tuple[str, ...] = (
    "remotive",
    "jobicy",
    "weworkremotely",
    "greenhouse",
    "ashby",
    "lever",
    "hackernews",
)
NATIONAL_SOURCES: tuple[str, ...] = ("github_br",)

SOURCE_ALIASES: dict[str, str] = {
    "hn": "hackernews",
    "hacker_news": "hackernews",
    "wwr": "weworkremotely",
    "github": "github_br",
    "gh": "github_br",
}

MinerFn = Callable[..., list[dict[str, Any]]]


def _get_miner_registry() -> dict[str, MinerFn]:
    return {
        "remotive": mine_remotive,
        "jobicy": mine_jobicy,
        "weworkremotely": mine_weworkremotely,
        "greenhouse": mine_greenhouse,
        "ashby": mine_ashby,
        "lever": mine_lever,
        "hackernews": mine_hackernews,
        "github_br": mine_github_brasil,
    }


def _invoke_miner(fn: MinerFn, use_cache: bool) -> list[dict[str, Any]]:
    params = inspect.signature(fn).parameters
    if "use_cache" in params:
        return fn(use_cache=use_cache)
    return fn()


def _resolve_sources(modo: str, fontes: list[str] | None) -> list[str]:
    registry = _get_miner_registry()
    if fontes:
        resolved: list[str] = []
        for raw in fontes:
            key = SOURCE_ALIASES.get(raw.strip().lower(), raw.strip().lower())
            if key in registry and key not in resolved:
                resolved.append(key)
        return resolved

    selected: list[str] = []
    if modo in ("todos", "internacional"):
        selected.extend(INTERNATIONAL_SOURCES)
    if modo in ("todos", "nacional"):
        selected.extend(NATIONAL_SOURCES)
    return selected


def calculate_stack_score(text: str, profile_skills: list[str]) -> tuple[int, list[str]]:
    """Calcula aderência da stack do candidato (0 a 100) com saída determinística."""
    text_lower = (text or "").lower()
    matches: set[str] = set()

    for skill in profile_skills:
        terms = re.split(r"[\s,\(\)/]+", skill.lower())
        for term in terms:
            if not term:
                continue
            if len(term) >= 3 or term in SHORT_TECH_SKILLS:
                if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
                    matches.add(term)
                    break

    sorted_matches = sorted(matches)
    score = min(100, int((len(sorted_matches) / 4.0) * 100))
    return score, sorted_matches


def mine_all_opportunities(
    profile_data: dict[str, Any] | CandidateProfile,
    modo: str = "todos",
    min_schedule: int = 50,
    min_stack: int = 25,
    fontes: list[str] | None = None,
    use_cache: bool = True,
    max_workers: int = 6,
) -> list[dict[str, Any]]:
    """
    Minera vagas concorrentemente nas fontes selecionadas, avalia conflitos de horário
    e ranqueia por compatibilidade de rotina (60%) e stack técnica (40%).
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    candidate_schedule = profile.horario_trabalho_desejado
    profile_skills = profile.competencias.principais + profile.competencias.secundarias

    selected_sources = _resolve_sources(modo, fontes)
    if not selected_sources:
        return []

    registry = _get_miner_registry()
    brutas: list[dict[str, Any]] = []

    worker_count = max(1, min(max_workers, len(selected_sources)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        submitted = [
            (src, executor.submit(_invoke_miner, registry[src], use_cache))
            for src in selected_sources
        ]
        for src_name, future in submitted:
            try:
                items = future.result()
                if isinstance(items, list):
                    brutas.extend(items)
            except Exception as exc:
                logger.warning("Coletor '%s' falhou durante execução: %s", src_name, exc)

    # Deduplicação por URL normalizada e por par (empresa, titulo)
    seen_urls: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    unicas: list[dict[str, Any]] = []

    for vaga in brutas:
        raw_url = str(vaga.get("url") or "").strip()
        if not raw_url:
            continue
        norm_url = raw_url.rstrip("/").lower()
        title_key = (
            str(vaga.get("empresa") or "").strip().lower(),
            str(vaga.get("titulo") or "").strip().lower(),
        )
        if norm_url in seen_urls or (title_key[0] and title_key[1] and title_key in seen_titles):
            continue
        seen_urls.add(norm_url)
        if title_key[0] and title_key[1]:
            seen_titles.add(title_key)
        unicas.append(vaga)

    qualificadas: list[dict[str, Any]] = []
    for vaga in unicas:
        texto_analise = (
            f"{vaga.get('titulo', '')} {vaga.get('descricao', '')} {vaga.get('resumo', '')}"
        )

        schedule_res = evaluate_schedule_fit(
            texto_analise,
            str(vaga.get("localizacao") or ""),
            str(vaga.get("tipo_contrato") or ""),
            candidate_schedule,
        )
        stack_score, matches = calculate_stack_score(texto_analise, profile_skills)
        score_composto = round(0.6 * schedule_res["score_horario"] + 0.4 * stack_score, 1)

        if schedule_res["score_horario"] < min_schedule or stack_score < min_stack:
            continue

        enriched = {
            **vaga,
            "schedule_fit": schedule_res,
            "stack_score": stack_score,
            "matches_stack": matches,
            "score_composto": score_composto,
        }
        validated = QualifiedJobOpportunity.model_validate(enriched)
        qualificadas.append(validated.model_dump())

    qualificadas.sort(
        key=lambda x: (
            x["score_composto"],
            x["schedule_fit"]["score_horario"],
            x["stack_score"],
        ),
        reverse=True,
    )
    return qualificadas
