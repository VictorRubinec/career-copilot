"""Mapeamento de formulários ATS, respostas de triagem, detecção de gates e log idempotente."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import atomic_write_json, get_applications_log_path
from ..models import (
    ApplicationFormFieldType,
    ApplicationPayload,
    CandidateProfile,
    CopilotSessionResult,
)
from ..tailor.pitch_generator import generate_cover_pitch

FIELD_SELECTOR_RULES: tuple[tuple[str, ApplicationFormFieldType, tuple[str, ...]], ...] = (
    (
        "first_name",
        "text",
        (
            'input[name="first_name"]',
            'input[id="first_name"]',
            'input[autocomplete="given-name"]',
            'input[name*="first" i]',
            'input[placeholder*="first name" i]',
        ),
    ),
    (
        "last_name",
        "text",
        (
            'input[name="last_name"]',
            'input[id="last_name"]',
            'input[autocomplete="family-name"]',
            'input[name*="last" i]',
            'input[placeholder*="last name" i]',
        ),
    ),
    (
        "full_name",
        "text",
        (
            'input[name="name"]',
            'input[id="name"]',
            'input[name*="full_name" i]',
            'input[name*="fullname" i]',
            'input[autocomplete="name"]',
            'input[placeholder*="full name" i]',
            'input[placeholder*="nome completo" i]',
        ),
    ),
    (
        "email",
        "email",
        (
            'input[type="email"]',
            'input[name="email"]',
            'input[id="email"]',
            'input[autocomplete="email"]',
            'input[name*="email" i]',
        ),
    ),
    (
        "phone",
        "tel",
        (
            'input[type="tel"]',
            'input[name*="phone" i]',
            'input[id*="phone" i]',
            'input[name*="telefone" i]',
            'input[autocomplete="tel"]',
        ),
    ),
    (
        "linkedin",
        "url",
        (
            'input[name*="linkedin" i]',
            'input[id*="linkedin" i]',
            'input[placeholder*="linkedin" i]',
            'input[aria-label*="linkedin" i]',
        ),
    ),
    (
        "github",
        "url",
        (
            'input[name*="github" i]',
            'input[id*="github" i]',
            'input[placeholder*="github" i]',
            'input[aria-label*="github" i]',
        ),
    ),
    (
        "portfolio",
        "url",
        (
            'input[name*="portfolio" i]',
            'input[name*="website" i]',
            'input[id*="website" i]',
            'input[placeholder*="portfolio" i]',
        ),
    ),
    (
        "location",
        "text",
        (
            'input[name*="location" i]',
            'input[id*="location" i]',
            'input[name*="city" i]',
            'input[placeholder*="location" i]',
            'input[placeholder*="cidade" i]',
        ),
    ),
    (
        "cover_letter",
        "textarea",
        (
            'textarea[name*="cover" i]',
            'textarea[id*="cover" i]',
            'textarea[name*="carta" i]',
            'textarea[placeholder*="cover letter" i]',
            'textarea[aria-label*="cover letter" i]',
        ),
    ),
    (
        "resume_pdf",
        "file",
        (
            'input[type="file"][name*="resume" i]',
            'input[type="file"][id*="resume" i]',
            'input[type="file"][name*="cv" i]',
            'input[type="file"]',
        ),
    ),
)

SCREENING_TEXTAREA_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "timezone",
            "time zone",
            "hours",
            "schedule",
            "availability",
            "async",
            "horário",
            "horario",
            "disponibilidade",
        ),
        "disponibilidade_horario",
    ),
    (
        ("salary", "compensation", "rate", "pay", "pretens", "remuner"),
        "pretensao_salarial",
    ),
    (
        ("contract", "b2b", "pj", "employment", "regime"),
        "regime_trabalho",
    ),
    (
        ("english", "language", "idioma", "inglês", "ingles"),
        "nivel_ingles",
    ),
)

_ANTIBOT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("reCAPTCHA", re.compile(r"g-recaptcha|google\.com/recaptcha", re.IGNORECASE)),
    ("hCaptcha", re.compile(r"h-captcha|hcaptcha\.com", re.IGNORECASE)),
    (
        "Cloudflare Turnstile",
        re.compile(r"cf-turnstile|challenges\.cloudflare\.com", re.IGNORECASE),
    ),
    (
        "Verificação anti-bot ('verify you are human')",
        re.compile(r"verify\s+you\s+are\s+human|captcha-delivery", re.IGNORECASE),
    ),
)

_LOGIN_WALL_TEXT_RE = re.compile(
    r"sign\s+in\s+to\s+apply|log\s*in\s+to\s+continue|fa[cç]a\s+login\s+para",
    re.IGNORECASE,
)
_PASSWORD_INPUT_RE = re.compile(r'<input[^>]*type=["\']password["\']', re.IGNORECASE)
_APP_FORM_EVIDENCE_RE = re.compile(
    r'type=["\']file["\']|first_name|cover_letter|apply',
    re.IGNORECASE,
)


def _split_full_name(full_name: str) -> tuple[str, str]:
    tokens = [part for part in (full_name or "").split() if part]
    if not tokens:
        return "Candidato", ""
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[0], " ".join(tokens[1:])


def _detect_pitch_language(job_data: dict[str, Any], idioma: str) -> str:
    if idioma in ("pt", "en"):
        return idioma
    origem = str(job_data.get("origem") or "").lower()
    local = str(job_data.get("localizacao") or "").lower()
    if "internacional" in origem or "usd" in origem or "eur" in origem:
        return "en"
    if re.search(r"\b(?:nacional|brl|pj)\b", origem):
        return "pt"
    if re.search(r"\b(?:brasil|brazil)\b", local):
        return "pt"
    return "en"


def build_application_payload(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any],
    pdf_path: str | Path | None = None,
    custom_answers: dict[str, str] | None = None,
    idioma: str = "auto",
) -> ApplicationPayload:
    """Monta payload completo e transparente para preenchimento assistido do formulário."""
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    candidato = profile.candidato
    contato = candidato.contato
    schedule = profile.horario_trabalho_desejado
    prefs = profile.preferencias_carreira

    primeiro_nome, sobrenome = _split_full_name(candidato.nome)
    pitch_bundle = generate_cover_pitch(profile, job_data)
    lang = _detect_pitch_language(job_data, idioma)
    carta = (
        pitch_bundle["pitch_portugues"]
        if lang == "pt"
        else pitch_bundle["pitch_ingles"]
    )

    janela_seg_sex = schedule.janela_disponivel.get("segunda_a_sexta", "19:00 - 00:00 (BRT)")
    janela_fds = schedule.janela_disponivel.get("finais_de_semana", "Sob demanda")
    if lang == "pt":
        disponibilidade = (
            f"Disponibilidade em regime async-first: Segunda a Sexta ({janela_seg_sex}) "
            f"e finais de semana ({janela_fds}), carga de {schedule.carga_semanal_horas}h/semana, "
            f"fuso {schedule.timezone_candidato}. Sem disponibilidade para reuniões síncronas fixas em horário comercial."
        )
    else:
        disponibilidade = (
            f"Async-first availability: Mon-Fri {janela_seg_sex} ({schedule.timezone_candidato}) "
            f"plus weekend sprint delivery ({janela_fds}), ~{schedule.carga_semanal_horas}h/week. "
            "No mandatory daytime synchronous standups between 09:00 and 18:00 BRT."
        )

    regimes = (
        ", ".join(prefs.regimes_contratuais[:2])
        if prefs.regimes_contratuais
        else "Contractor B2B / Async Remote"
    )
    comp = prefs.remuneracao_minima
    if lang == "pt" and (comp.brl_hora > 0 or comp.brl_mensal > 0):
        pretensao = f"R$ {comp.brl_hora:.0f}/h (~R$ {comp.brl_mensal:.0f}/mês PJ)"
    elif comp.usd_hora > 0 or comp.usd_mensal > 0:
        pretensao = f"${comp.usd_hora:.0f}/hour USD (~${comp.usd_mensal:.0f}/month Contractor)"
    else:
        pretensao = "Open / Market rate"

    respostas_triagem = {
        "disponibilidade_horario": disponibilidade,
        "regime_trabalho": regimes,
        "localizacao_fuso": f"{candidato.localizacao} ({schedule.timezone_candidato})".strip(),
        "pretensao_salarial": pretensao,
        "nivel_ingles": profile.competencias.idiomas.get(
            "ingles", "Technical / Fluent async written communication"
        ),
    }
    if custom_answers:
        for k, v in custom_answers.items():
            respostas_triagem[str(k)] = str(v)

    resolved_pdf = str(pdf_path) if pdf_path is not None else None
    return ApplicationPayload(
        vaga_id=str(job_data.get("id") or ""),
        vaga_titulo=str(job_data.get("titulo") or "Software Engineer"),
        empresa=str(job_data.get("empresa") or "Target Company"),
        url_candidatura=str(job_data.get("url") or "").strip(),
        nome_completo=candidato.nome,
        primeiro_nome=primeiro_nome,
        sobrenome=sobrenome,
        email=contato.email,
        telefone=contato.telefone,
        localizacao=candidato.localizacao,
        linkedin=contato.linkedin,
        github=contato.github,
        portfolio=contato.portfolio,
        curriculo_pdf_path=resolved_pdf,
        carta_apresentacao=carta,
        respostas_triagem=respostas_triagem,
    )


def detect_external_gate(page_url: str, page_html: str) -> str | None:
    """Detecta CAPTCHAs, desafios anti-bot ou paredes de login sem tentar contorná-los."""
    combined = f"{page_url or ''}\n{page_html or ''}"
    for label, pattern in _ANTIBOT_PATTERNS:
        if pattern.search(combined):
            return (
                f"Desafio de verificação humana ({label}) detectado. "
                "Complete manualmente no navegador antes de prosseguir."
            )

    url_lower = (page_url or "").lower()
    html_lower = (page_html or "").lower()
    has_app_form = bool(_APP_FORM_EVIDENCE_RE.search(html_lower))

    if (
        ("/login" in url_lower or "/signin" in url_lower or _LOGIN_WALL_TEXT_RE.search(html_lower))
        and not has_app_form
    ) or (_PASSWORD_INPUT_RE.search(html_lower) and not has_app_form):
        return (
            "Parede de autenticação / login obrigatório detectada. "
            "Autentique-se manualmente no perfil persistente do navegador."
        )

    return None


def normalize_application_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def _load_log_entries(target_path: Path) -> list[dict[str, Any]]:
    if not target_path.exists():
        return []
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def has_prior_application_for_url(url: str, log_path: Path | None = None) -> bool:
    """Verifica no registro local se já existe rascunho/sessão prévia para esta URL."""
    norm = normalize_application_url(url)
    if not norm:
        return False
    target = log_path if log_path is not None else get_applications_log_path()
    entries = _load_log_entries(target)
    return any(
        normalize_application_url(str(item.get("url_destino") or "")) == norm
        for item in entries
        if isinstance(item, dict)
    )


def record_application_draft(
    result: CopilotSessionResult,
    payload: ApplicationPayload,
    log_path: Path | None = None,
) -> None:
    """Registra sessão assistida de forma atômica para auditoria e controle de duplicatas."""
    target = log_path if log_path is not None else get_applications_log_path()
    entries = _load_log_entries(target)
    entries.append(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "vaga_id": payload.vaga_id,
            "vaga_alvo": result.vaga_alvo,
            "url_destino": result.url_destino,
            "status": result.status,
            "submetido_automaticamente": result.submetido_automaticamente,
            "curriculo_pdf_path": result.curriculo_pdf_path,
            "campos_preenchidos_count": sum(1 for c in result.campos_preenchidos if c.preenchido),
            "campos_pendentes_humano": result.campos_pendentes_humano,
            "bloqueio_externo_detectado": result.bloqueio_externo_detectado,
        }
    )
    atomic_write_json(target, entries)
