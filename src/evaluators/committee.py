"""Banca Examinadora Cognitiva (The 7 Personas Hiring Board) com Structured Outputs."""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from ..config import get_logger
from ..models import (
    ALL_PERSONA_IDS,
    CandidateProfile,
    CommitteeEvaluationResult,
    CommitteePersonaBatch,
    CommitteeVerdict,
    CommitteeVetoDetail,
    EvaluationMode,
    PersonaEvaluation,
    PersonaId,
    ScheduleFitResult,
)
from ..profiler.analyzer import analyze_career_profile
from ..profiler.gap_detector import TECH_KEYWORDS, detect_job_gaps
from ..tailor.resume_calibrator import calibrate_resume_for_job
from .schedule_matcher import evaluate_schedule_fit

logger = get_logger(__name__)

APPROVAL_MEAN_THRESHOLD: float = 8.0
CRITICAL_VETO_THRESHOLD: float = 7.0
CRITICAL_VETO_PERSONAS: tuple[PersonaId, ...] = ("ats_screener", "skeptic_recruiter")
REQUIRED_PERSONA_IDS: tuple[PersonaId, ...] = ALL_PERSONA_IDS

CommitteeLLMProvider = Callable[[str, type[CommitteePersonaBatch]], CommitteePersonaBatch]

_PERSONA_LABELS: dict[PersonaId, str] = {
    "ats_screener": "ATS Screener",
    "tech_recruiter": "Tech Recruiter",
    "engineering_manager": "Engineering Manager",
    "senior_peer": "Senior Peer Developer",
    "product_manager": "Product Manager",
    "cto_head": "CTO / Head",
    "skeptic_recruiter": "Recrutador Cético",
}

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_ATS_HOSTILE_HTML_RE = re.compile(r"<\s*(?:table|div|img|svg|iframe)\b", re.IGNORECASE)
_MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$\n\s*\|[\s:-]+\|", re.MULTILINE)
_BULLET_LINE_RE = re.compile(r"^\s*[-*•]\s+(.+)$", re.MULTILINE)
_METRIC_RE = re.compile(
    r"(?:\d+(?:[.,]\d+)?\s*%|\b\d+(?:\.\d+)?x\b|(?:R\$|\$|€)\s*\d+|"
    r"\b\d+\s*(?:ms|s|min|h|horas?|hours?|dias?|days?|meses?|months?|"
    r"usu[aá]rios?|users?|clientes?|clients?|tickets?|req/s|rps|mil|k)\b)",
    re.IGNORECASE,
)
_OUTCOME_VERB_RE = re.compile(
    r"\b(?:reduz\w*|reduc\w*|elimin\w*|aceler\w*|accelerat\w*|aument\w*|increas\w*|"
    r"economiz\w*|sav\w*|otimiz\w*|optimiz\w*|garanti\w*|ensur\w*|melhor\w*|improv\w*|"
    r"disponibilidade|uptime|sla|kpi|roi|receita|revenue|custo|cost|impact\w*|"
    r"entrega\w*|deliver\w*|clientes?|clients?|stakeholders?)\b",
    re.IGNORECASE,
)
_CLICHE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("proativo", re.compile(r"\bproativ[oa]\b", re.IGNORECASE)),
    ("dinâmico", re.compile(r"\bdin[aâ]mic[oa]\b", re.IGNORECASE)),
    ("apaixonado por tecnologia", re.compile(r"\bapaixonad[oa]\s+por\s+tecnologia\b", re.IGNORECASE)),
    ("pensar fora da caixa", re.compile(r"\bpensar\s+fora\s+da\s+caixa\b", re.IGNORECASE)),
    ("ninja/rockstar/guru", re.compile(r"\b(?:ninja|rockstar|guru)\b", re.IGNORECASE)),
    ("vestir a camisa", re.compile(r"\bvestir\s+a\s+camisa\b", re.IGNORECASE)),
    ("workaholic", re.compile(r"\bworkaholic\b", re.IGNORECASE)),
    ("team player", re.compile(r"\bteam\s+player\b", re.IGNORECASE)),
    ("fast learner", re.compile(r"\bfast\s+learner\b", re.IGNORECASE)),
    ("sinergia", re.compile(r"\bsinergia\b", re.IGNORECASE)),
    ("10x engineer", re.compile(r"\b10x\s+engineer\b", re.IGNORECASE)),
)
_PLACEHOLDER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("placeholder genérico", re.compile(r"\b(?:lorem\s+ipsum|insert\s+here|placeholder)\b", re.IGNORECASE)),
    ("template 'Seu Nome Completo'", re.compile(r"\bseu\s+nome\s+completo\b", re.IGNORECASE)),
    ("template 'Empresa Anterior'", re.compile(r"\bempresa\s+anterior\b", re.IGNORECASE)),
    ("template 'dev@exemplo.com'", re.compile(r"dev@exemplo\.com", re.IGNORECASE)),
    ("marcação [TODO]", re.compile(r"\[todo\]", re.IGNORECASE)),
)


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, float(value))), 1)


def _extract_experience_bullets(resume_markdown: str) -> list[str]:
    """Extrai bullets fora das seções de Competências e Formação para análise de impacto."""
    bullets: list[str] = []
    in_non_experience_list = False
    for raw_line in resume_markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            header_lower = line.lower()
            in_non_experience_list = any(
                k in header_lower
                for k in ("competências", "competencias", "skills", "formação", "formacao", "education", "certifica")
            )
            continue
        match = _BULLET_LINE_RE.match(line)
        if match and not in_non_experience_list:
            bullets.append(match.group(1).strip())
    return bullets


def _evaluate_ats_screener(
    resume_markdown: str,
    job_data: dict[str, Any],
) -> PersonaEvaluation:
    resume_lower = resume_markdown.lower()
    job_text = f"{job_data.get('titulo', '')} {job_data.get('descricao', job_data.get('resumo', ''))}".lower()

    required_keywords = [
        kw for kw in TECH_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", job_text)
    ]
    for m in job_data.get("matches_stack", []):
        m_low = str(m).strip().lower()
        if m_low and m_low not in required_keywords:
            required_keywords.append(m_low)

    matched_in_resume = [
        kw for kw in required_keywords if re.search(r"\b" + re.escape(kw) + r"\b", resume_lower)
    ]
    missing_in_resume = [kw for kw in required_keywords if kw not in matched_in_resume]

    if required_keywords:
        keyword_ratio = len(matched_in_resume) / len(required_keywords)
    else:
        resume_tech_hits = [
            kw for kw in TECH_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", resume_lower)
        ]
        keyword_ratio = min(1.0, len(resume_tech_hits) / 4.0)

    has_headings = bool(re.search(r"^#\s+.+", resume_markdown, re.MULTILINE)) and bool(
        re.search(r"^##\s+.+", resume_markdown, re.MULTILINE)
    )
    has_email = bool(_EMAIL_RE.search(resume_markdown))
    word_count = len(resume_markdown.split())
    has_hostile_layout = bool(
        _ATS_HOSTILE_HTML_RE.search(resume_markdown) or _MARKDOWN_TABLE_RE.search(resume_markdown)
    )

    score = 4.5 + (4.2 * keyword_ratio)
    pontos_fortes: list[str] = []
    lacunas: list[str] = []
    acoes: list[str] = []

    if matched_in_resume:
        pontos_fortes.append(
            f"Aderência de {round(keyword_ratio * 100)}% às palavras-chave da vaga ({', '.join(matched_in_resume[:6])})."
        )
    if missing_in_resume:
        lacunas.append(f"Keywords ausentes no currículo: {', '.join(missing_in_resume[:5])}.")
        acoes.append(
            f"Incorporar termos técnicos comprovados ausentes ({', '.join(missing_in_resume[:4])}) no resumo e experiências."
        )

    if has_headings:
        score += 0.6
        pontos_fortes.append("Hierarquia Markdown limpa (# / ##) compatível com parsers ATS.")
    else:
        score -= 1.2
        lacunas.append("Ausência de cabeçalhos estruturados (# / ##) prejudica indexação por seções.")
        acoes.append("Organizar o currículo com cabeçalhos padrão (# Nome, ## Resumo, ## Experiência).")

    if has_email:
        score += 0.5
    else:
        score -= 0.8
        lacunas.append("E-mail de contato ausente ou ilegível para parser ATS.")
        acoes.append("Incluir endereço de e-mail válido no cabeçalho principal.")

    if 110 <= word_count <= 950:
        score += 0.2
    elif word_count < 80:
        score -= 2.5
        lacunas.append(f"Densidade textual insuficiente ({word_count} palavras) para ranqueamento ATS.")
        acoes.append("Expandir descrição de entregas técnicas e competências para 200-600 palavras.")
    elif word_count < 110:
        score -= 0.8
        lacunas.append(f"Currículo curto ({word_count} palavras) com baixa superfície de indexação.")
        acoes.append("Detalhar realizações e tecnologias aplicadas em cada experiência.")
    else:
        score -= 0.5
        lacunas.append(f"Currículo extenso ({word_count} palavras); risco de truncamento.")
        acoes.append("Sintetizar experiências antigas para manter foco em 1-2 páginas.")

    if has_hostile_layout:
        score -= 2.8
        lacunas.append("Uso de tabelas Markdown/HTML complexo (<table>/<div>) quebra a leitura de parsers ATS.")
        acoes.append("Remover tabelas e tags HTML de layout, mantendo texto linear em Markdown puro.")

    nota = _clamp_score(score)
    return PersonaEvaluation(
        persona_id="ats_screener",
        persona_nome=_PERSONA_LABELS["ats_screener"],
        nota=nota,
        foco_avaliacao="Densidade de keywords técnicas e legibilidade estrutural por parsers ATS.",
        pontos_fortes=pontos_fortes,
        lacunas_e_riscos=lacunas,
        acoes_corretivas=acoes,
        justificativa=(
            f"Parser ATS registrou {round(keyword_ratio * 100)}% de cobertura de keywords "
            f"em {word_count} palavras; estrutura {'limpa' if not has_hostile_layout else 'com elementos hostis'}."
        ),
    )


def _evaluate_tech_recruiter(
    resume_markdown: str,
    job_data: dict[str, Any],
    career_diagnosis: dict[str, Any],
) -> PersonaEvaluation:
    non_empty_lines = [ln.strip() for ln in resume_markdown.splitlines() if ln.strip()]
    top_fold = "\n".join(non_empty_lines[:12])
    top_lower = top_fold.lower()

    has_name_heading = bool(non_empty_lines and non_empty_lines[0].startswith("# "))
    has_summary_top = (
        len(non_empty_lines) >= 2
        and ("resumo" in top_lower or "summary" in top_lower or "**" in non_empty_lines[1])
    )
    has_contact_top = bool(_EMAIL_RE.search(top_fold) or "linkedin" in top_lower or "github" in top_lower)
    section_count = len(re.findall(r"^##\s+.+", resume_markdown, re.MULTILINE))
    exp_bullets = _extract_experience_bullets(resume_markdown)
    all_bullets = exp_bullets if exp_bullets else _BULLET_LINE_RE.findall(resume_markdown)
    avg_bullet_words = (
        sum(len(b.split()) for b in all_bullets) / len(all_bullets) if all_bullets else 0.0
    )
    word_count = len(resume_markdown.split())

    senioridade_est = career_diagnosis["diagnostico_carreira"]["senioridade_estimada"].lower()
    titulo_vaga = str(job_data.get("titulo") or "").lower()

    score = 6.2
    pontos_fortes: list[str] = []
    lacunas: list[str] = []
    acoes: list[str] = []

    if has_name_heading and has_summary_top:
        score += 1.0
        pontos_fortes.append("Topo do currículo comunica nome, título e posicionamento em < 6 segundos.")
    else:
        lacunas.append("Topo do currículo sem título ou resumo claro na primeira dobra.")
        acoes.append("Posicionar nome, cargo-alvo e resumo executivo nas 5 primeiras linhas.")

    if has_contact_top and ("linkedin" in top_lower or "github" in top_lower):
        score += 0.8
        pontos_fortes.append("Contatos e links profissionais visíveis logo no cabeçalho.")
    elif has_contact_top:
        score += 0.4
        lacunas.append("Faltam links clicáveis de portfólio/GitHub/LinkedIn no cabeçalho.")
        acoes.append("Adicionar links diretos de GitHub e LinkedIn abaixo do nome.")
    else:
        lacunas.append("Contatos ou links (LinkedIn/GitHub) pouco evidentes na primeira dobra.")
        acoes.append("Adicionar e-mail e link clicável de LinkedIn/GitHub abaixo do nome.")

    if len(exp_bullets) >= 3 and avg_bullet_words <= 42:
        score += 1.0
        pontos_fortes.append(f"Boa escaneabilidade visual ({len(exp_bullets)} bullets de entrega concisos).")
    elif len(all_bullets) >= 1:
        score += 0.2
        if len(exp_bullets) < 3:
            lacunas.append(f"Poucos bullets de entrega em experiência ({len(exp_bullets)}); leitura superficial em 6s.")
            acoes.append("Detalhar ao menos 3 bullets objetivos de entregas na experiência recente.")
        if avg_bullet_words > 45:
            score -= 0.8
            lacunas.append("Bullets excessivamente longos reduzem leitura rápida em triagem de 6 segundos.")
            acoes.append("Encurtar bullets para no máximo 2 linhas (15-30 palavras) com verbo de ação.")
    else:
        score -= 1.2
        lacunas.append("Blocos corridos sem bullet points dificultam a triagem visual.")
        acoes.append("Converter parágrafos de experiência em bullet points objetivos.")

    if section_count >= 3 and word_count >= 100:
        score += 0.5

    if "júnior" in senioridade_est and any(
        lvl in titulo_vaga for lvl in ("staff", "principal", "director", "head", "vp")
    ):
        score -= 2.2
        lacunas.append("Desalinhamento severo entre senioridade do perfil (Júnior) e vaga (Staff/Principal).")
        acoes.append("Ajustar alvo para vagas Júnior/Pleno ou evidenciar liderança técnica equivalente.")
    elif "júnior" in senioridade_est and any(lvl in titulo_vaga for lvl in ("senior", "sênior", "lead")):
        score -= 1.2
        lacunas.append("Vaga pede senioridade Sênior/Lead acima da estimativa atual do perfil.")
        acoes.append("Destacar entregas autônomas em produção e arquitetura para reduzir gap de senioridade.")

    nota = _clamp_score(score)
    return PersonaEvaluation(
        persona_id="tech_recruiter",
        persona_nome=_PERSONA_LABELS["tech_recruiter"],
        nota=nota,
        foco_avaliacao="Regra dos 6 segundos, clareza visual e aderência de senioridade.",
        pontos_fortes=pontos_fortes,
        lacunas_e_riscos=lacunas,
        acoes_corretivas=acoes,
        justificativa=(
            f"Triagem de 6s encontrou {section_count} seções e {len(all_bullets)} bullets "
            f"(média de {round(avg_bullet_words, 1)} palavras/bullet); senioridade estimada: "
            f"{career_diagnosis['diagnostico_carreira']['senioridade_estimada']}."
        ),
    )


def _evaluate_engineering_manager(
    resume_markdown: str,
    gap_report: dict[str, Any],
) -> PersonaEvaluation:
    # Avalia exclusivamente a profundidade técnica evidenciada no currículo apresentado
    corpus = resume_markdown.lower()

    pillars: list[tuple[str, tuple[str, ...]]] = (
        ("Arquitetura & APIs Backend", ("arquitet", "architect", "api", "rest", "graphql", "microserv", "backend", "fastapi", "django", "spring")),
        ("Pipelines de Dados & SQL", ("etl", "pipeline", "sql", "postgres", "mysql", "redis", "dados", "data", "saneamento")),
        ("Concorrência, Async & Automação", ("async", "assíncron", "concurr", "celery", "kafka", "rabbitmq", "queue", "worker", "event-driven", "distribu", "selenium", "playwright", "automa")),
        ("Confiabilidade & Troubleshooting", ("incidente", "troubleshooting", "produç", "production", "resilien", "health check", "failover", "timeout", "backoff")),
        ("Ownership Ponta a Ponta", ("ponta a ponta", "end-to-end", "e2e", "desenvolveu", "construiu", "built", "designed", "owned", "architected", "led")),
    )

    hits: list[str] = []
    misses: list[str] = []
    for label, tokens in pillars:
        if any(tok in corpus for tok in tokens):
            hits.append(label)
        else:
            misses.append(label)

    match_pct = float(gap_report["aderencia_tecnica"]["match_pct"])
    score = 5.4 + (0.65 * len(hits)) + (0.9 * (match_pct / 100.0))

    pontos_fortes = [f"Evidência técnica em: {', '.join(hits)}."] if hits else []
    lacunas: list[str] = []
    acoes: list[str] = []
    if misses:
        lacunas.append(f"Pilares pouco detalhados no texto: {', '.join(misses[:3])}.")
        acoes.append(
            f"Explicitar decisões técnicas e escala em {misses[0]} nos projetos recentes."
        )
    gaps_stack = gap_report["aderencia_tecnica"]["gaps_identificados"]
    if gaps_stack:
        lacunas.append(f"Gaps técnicos frente à vaga: {', '.join(gaps_stack[:4])}.")
        acoes.append(f"Mapear experiência equivalente ou plano de rampa para {', '.join(gaps_stack[:3])}.")

    nota = _clamp_score(score)
    return PersonaEvaluation(
        persona_id="engineering_manager",
        persona_nome=_PERSONA_LABELS["engineering_manager"],
        nota=nota,
        foco_avaliacao="Arquitetura, concorrência/assincronia, confiabilidade e profundidade técnica.",
        pontos_fortes=pontos_fortes,
        lacunas_e_riscos=lacunas,
        acoes_corretivas=acoes,
        justificativa=(
            f"Cobertura de {len(hits)}/5 pilares de engenharia e {match_pct}% de aderência técnica à vaga."
        ),
    )


def _evaluate_senior_peer(resume_markdown: str) -> PersonaEvaluation:
    corpus = resume_markdown.lower()
    bullets = _extract_experience_bullets(resume_markdown)

    has_tests = any(
        tok in corpus
        for tok in ("pytest", "unittest", "selenium", "playwright", "testes", "testing", "e2e", "end-to-end", "tdd", "qa", "cobertura", "coverage")
    )
    has_cicd = any(
        tok in corpus
        for tok in ("git", "github actions", "gitlab ci", "ci/cd", "docker", "kubernetes", "linux", "shell", "cron", "deploy")
    )
    has_quality = any(
        tok in corpus
        for tok in ("pull request", "code review", "typing", "pydantic", "clean", "refactor", "lint", "api", "sql", "pr")
    )

    pillars_hit = sum((has_tests, has_cicd, has_quality))
    tech_bullets = sum(
        1 for b in bullets if any(kw in b.lower() for kw in ("python", "sql", "docker", "api", "test", "playwright", "selenium", "shell", "git", "ci"))
    )

    score = 5.8 + (1.0 * pillars_hit)
    if tech_bullets >= 4:
        score += 0.5
    if has_tests and has_cicd:
        score += 0.4

    pontos_fortes: list[str] = []
    lacunas: list[str] = []
    acoes: list[str] = []

    if has_tests:
        pontos_fortes.append("Prática comprovada com testes automatizados / validação end-to-end.")
    else:
        lacunas.append("Sem menção explícita a suíte de testes automatizados (pytest, E2E, cobertura).")
        acoes.append("Incluir resultados de cobertura de testes automatizados (pytest/Playwright).")

    if has_cicd:
        pontos_fortes.append("Vivência em containers, Linux/Shell ou pipelines CI/CD.")
    else:
        lacunas.append("Ausência de menções a CI/CD, versionamento Git ou containerização (Docker).")
        acoes.append("Destacar automação de build/deploy via GitHub Actions e Docker.")

    if has_quality:
        pontos_fortes.append("Indícios de boas práticas de contrato de código/APIs/PRs.")
    else:
        lacunas.append("Faltam sinais de qualidade de código (tipagem, revisão de PRs, padrões de API).")
        acoes.append("Mencionar revisão assíncrona de PRs, tipagem estrita ou contratos de dados.")

    nota = _clamp_score(score)
    return PersonaEvaluation(
        persona_id="senior_peer",
        persona_nome=_PERSONA_LABELS["senior_peer"],
        nota=nota,
        foco_avaliacao="Qualidade de código, testes automatizados, versionamento e CI/CD.",
        pontos_fortes=pontos_fortes,
        lacunas_e_riscos=lacunas,
        acoes_corretivas=acoes,
        justificativa=(
            f"Peer técnico validou {pillars_hit}/3 pilares de craftsmanship "
            f"(testes={'sim' if has_tests else 'não'}, CI/CD={'sim' if has_cicd else 'não'}) "
            f"e {tech_bullets} bullets técnicos concretos."
        ),
    )


def _evaluate_product_manager(resume_markdown: str) -> PersonaEvaluation:
    exp_bullets = _extract_experience_bullets(resume_markdown)
    target_lines = exp_bullets if exp_bullets else [
        ln.strip() for ln in resume_markdown.splitlines() if ln.strip()
    ]

    quantified_count = sum(1 for line in target_lines if _METRIC_RE.search(line))
    outcome_count = sum(1 for line in target_lines if _OUTCOME_VERB_RE.search(line))

    score = 5.6
    if quantified_count >= 3:
        score += 2.8
    elif quantified_count == 2:
        score += 2.1
    elif quantified_count == 1:
        score += 1.3

    if outcome_count >= 3:
        score += 1.1
    elif outcome_count >= 1:
        score += 0.6

    pontos_fortes: list[str] = []
    lacunas: list[str] = []
    acoes: list[str] = []

    if quantified_count >= 2:
        pontos_fortes.append(
            f"{quantified_count} entregas quantificadas com métricas concretas no padrão Google XYZ."
        )
    else:
        lacunas.append(
            f"Baixa quantificação de resultados ({quantified_count} bullet(s) com números/percentuais/%/tempo)."
        )
        acoes.append(
            "Reescrever bullets no formato Google XYZ: 'Alcançou [X]% de ganho medido por [Y] ao implementar [Z]'."
        )

    if outcome_count >= 2:
        pontos_fortes.append(
            f"Linguagem orientada a valor e impacto operacional ({outcome_count} ocorrências)."
        )
    else:
        lacunas.append("Descrição focada em tarefas técnicas sem evidenciar impacto para negócio/usuário.")
        acoes.append("Conectar cada automação/API a redução de tempo, custo, falhas ou SLA.")

    nota = _clamp_score(score)
    return PersonaEvaluation(
        persona_id="product_manager",
        persona_nome=_PERSONA_LABELS["product_manager"],
        nota=nota,
        foco_avaliacao="Métricas de negócio, impacto mensurável (Google XYZ) e entrega de valor.",
        pontos_fortes=pontos_fortes,
        lacunas_e_riscos=lacunas,
        acoes_corretivas=acoes,
        justificativa=(
            f"Identificados {quantified_count} bullets quantificados e {outcome_count} marcadores "
            f"de impacto de negócio/produto."
        ),
    )


def _evaluate_cto_head(
    resume_markdown: str,
    career_diagnosis: dict[str, Any],
) -> PersonaEvaluation:
    corpus = resume_markdown.lower()
    has_observability = any(
        tok in corpus
        for tok in ("monitor", "logs", "observab", "health check", "métricas", "metrics", "datadog", "grafana", "disponibilidade", "uptime")
    )
    has_governance = any(
        tok in corpus
        for tok in ("governan", "governance", "seguran", "security", "compliance", "six sigma", "melhoria contínua", "documenta", "documentation", "padroniz")
    )
    has_cloud_scale = any(
        tok in corpus
        for tok in ("docker", "aws", "gcp", "azure", "kubernetes", "terraform", "cloud", "infra", "escal", "scalab")
    )
    readiness_score = int(
        career_diagnosis["diagnostico_carreira"]["readiness_internacional_score"]
    )
    async_viability = career_diagnosis["analise_horario_trabalho"]["status"] == "ALTA"
    has_async_maturity = readiness_score >= 80 and async_viability

    pillars_hit = sum((has_observability, has_governance, has_cloud_scale, has_async_maturity))
    score = 5.8 + (0.9 * pillars_hit)

    pontos_fortes: list[str] = []
    lacunas: list[str] = []
    acoes: list[str] = []

    if has_observability:
        pontos_fortes.append("Preocupação com observabilidade, logs e disponibilidade em produção.")
    else:
        lacunas.append("Faltam sinais explícitos de observabilidade/SLOs (logs estruturados, alertas).")
        acoes.append("Evidenciar práticas de monitoramento, health checks ou redução de MTTR.")

    if has_governance:
        pontos_fortes.append("Maturidade de processo, documentação e melhoria contínua.")
    else:
        lacunas.append("Pouca evidência de governança técnica, segurança ou padronização de processos.")
        acoes.append("Destacar documentação assíncrona, runbooks ou padrões de segurança/qualidade.")

    if has_cloud_scale:
        pontos_fortes.append("Base em infraestrutura/containers compatível com ambientes escaláveis.")
    else:
        lacunas.append("Exposição limitada a cloud/containers/infraestrutura distribuída.")
        acoes.append("Explicitar experiência com Docker, ambientes cloud ou automação de infraestrutura.")

    if has_async_maturity:
        pontos_fortes.append(
            f"Prontidão internacional ({readiness_score}/100) e disciplina assíncrona sólida."
        )

    nota = _clamp_score(score)
    return PersonaEvaluation(
        persona_id="cto_head",
        persona_nome=_PERSONA_LABELS["cto_head"],
        nota=nota,
        foco_avaliacao="Governança técnica, observabilidade, escalabilidade e maturidade assíncrona.",
        pontos_fortes=pontos_fortes,
        lacunas_e_riscos=lacunas,
        acoes_corretivas=acoes,
        justificativa=(
            f"Avaliação executiva contabilizou {pillars_hit}/4 pilares estratégicos e "
            f"prontidão internacional de {readiness_score}/100."
        ),
    )


def _evaluate_skeptic_recruiter(
    resume_markdown: str,
    job_data: dict[str, Any],
    profile: CandidateProfile,
    schedule_fit: ScheduleFitResult,
) -> PersonaEvaluation:
    score = 9.4
    pontos_fortes: list[str] = []
    lacunas: list[str] = []
    acoes: list[str] = []

    # 1. Consistência de rotina noturna / moonlighting
    if schedule_fit.status == "INCOMPATIVEL":
        score -= 4.5
        flags_txt = ", ".join(schedule_fit.red_flags) if schedule_fit.red_flags else "horário diurno rígido"
        lacunas.append(f"Conflito crítico de rotina/moonlighting detectado: {flags_txt}.")
        acoes.append("Descartar vaga ou negociar formalmente regime 100% assíncrono antes de aplicar.")
    elif schedule_fit.status == "PARCIALMENTE_COMPATIVEL":
        score -= 1.4 + (0.4 * len(schedule_fit.red_flags))
        lacunas.append("Rotina parcialmente compatível exige validação prévia de cerimônias síncronas.")
        acoes.append("Confirmar com o recrutador ausência de dailies obrigatórias entre 09h e 18h BRT.")
    else:
        pontos_fortes.append("Compatibilidade horária consistente para atuação noturna/assíncrona.")

    # 2. Caça a clichês e buzzwords vazios
    cliches_found = [
        label for label, pat in _CLICHE_PATTERNS if pat.search(resume_markdown)
    ]
    if cliches_found:
        score -= min(4.0, 1.2 * len(cliches_found))
        lacunas.append(f"Clichês sem lastro técnico encontrados: {', '.join(cliches_found)}.")
        acoes.append(f"Substituir buzzwords ({', '.join(cliches_found)}) por evidências verificáveis.")
    else:
        pontos_fortes.append("Texto objetivo, livre de clichês genéricos e adjetivos vazios.")

    # 3. Restos de template / placeholders
    placeholders_found = [
        label for label, pat in _PLACEHOLDER_PATTERNS if pat.search(resume_markdown)
    ]
    if placeholders_found:
        score -= 3.2
        lacunas.append(f"Resquícios de template detectados: {', '.join(placeholders_found)}.")
        acoes.append("Preencher todos os dados reais do candidato e remover textos de exemplo.")

    # 4. Contradições de senioridade vs histórico
    title_claimed = f"{profile.candidato.titulo_principal} {resume_markdown[:250]}".lower()
    if not profile.historico_profissional and any(
        k in title_claimed for k in ("senior", "sênior", "staff", "lead", "principal", "arquiteto")
    ):
        score -= 2.8
        lacunas.append("Título alega senioridade avançada sem histórico profissional comprovado.")
        acoes.append("Incluir histórico profissional real compatível ou alinhar título ao nível atual.")

    exp_bullets = _extract_experience_bullets(resume_markdown)
    total_skills = len(profile.competencias.principais) + len(profile.competencias.secundarias)
    if total_skills >= 6 and (len(exp_bullets) < 2 or (len(exp_bullets) < 3 and len(resume_markdown.split()) < 100)):
        score -= 1.5
        lacunas.append("Muitas skills declaradas com pouca comprovação em bullets de experiência.")
        acoes.append("Vincular cada competência listada a entregas concretas no histórico.")

    # 5. Idioma em vagas internacionais
    is_intl_job = "internacional" in str(job_data.get("origem", "")).lower() or any(
        w in str(job_data.get("descricao", "")).lower() for w in ("the ", "with ", "experience", "remote")
    )
    ingles_level = profile.competencias.idiomas.get("ingles", "").lower()
    if is_intl_job and any(b in ingles_level for b in ("básico", "basico", "iniciante", "basic")):
        score -= 1.6
        lacunas.append("Vaga internacional em inglês com nível declarado insuficiente para comunicação assíncrona.")
        acoes.append("Preparar glossário técnico e validar escrita assíncrona antes da candidatura.")

    nota = _clamp_score(score)
    return PersonaEvaluation(
        persona_id="skeptic_recruiter",
        persona_nome=_PERSONA_LABELS["skeptic_recruiter"],
        nota=nota,
        foco_avaliacao="Detecção de clichês, contradições curriculares e colisões de rotina diurna.",
        pontos_fortes=pontos_fortes,
        lacunas_e_riscos=lacunas,
        acoes_corretivas=acoes,
        justificativa=(
            f"Auditoria cética identificou {len(cliches_found)} clichê(s), "
            f"{len(placeholders_found)} placeholder(s) e status de rotina {schedule_fit.classificacao_exibicao}."
        ),
    )


def compute_committee_consensus(
    avaliacoes: list[PersonaEvaluation],
    schedule_fit: ScheduleFitResult,
    vaga_alvo: str,
    modo_avaliacao: EvaluationMode = "heuristico_deterministico",
) -> CommitteeEvaluationResult:
    """
    Aplica a regra oficial de consenso da Banca Examinadora:
    - Aprovação requer média geral >= 8.0/10
    - Veto técnico automático se ATS Screener < 7.0 ou Recrutador Cético < 7.0
    """
    batch = CommitteePersonaBatch(avaliacoes=avaliacoes)
    by_id = {item.persona_id: item for item in batch.avaliacoes}
    ordered = [
        by_id[pid].model_copy(update={"nota": _clamp_score(by_id[pid].nota)})
        for pid in REQUIRED_PERSONA_IDS
    ]

    media_geral = round(sum(p.nota for p in ordered) / len(ordered), 2)

    personas_vetadoras: list[PersonaId] = []
    motivos_veto: list[str] = []
    for pid in CRITICAL_VETO_PERSONAS:
        persona = next(p for p in ordered if p.persona_id == pid)
        if persona.nota < CRITICAL_VETO_THRESHOLD:
            personas_vetadoras.append(pid)
            detalhe = persona.lacunas_e_riscos[0] if persona.lacunas_e_riscos else persona.justificativa
            motivos_veto.append(
                f"{persona.persona_nome} atribuiu {persona.nota:.1f}/10 (< {CRITICAL_VETO_THRESHOLD:.1f}): {detalhe}"
            )

    veto = CommitteeVetoDetail(
        ativo=bool(personas_vetadoras),
        personas_vetadoras=personas_vetadoras,
        motivos=motivos_veto,
    )

    veredito: CommitteeVerdict
    if veto.ativo:
        veredito = "VETADO"
        aprovado = False
    elif media_geral >= APPROVAL_MEAN_THRESHOLD:
        veredito = "APROVADO"
        aprovado = True
    else:
        veredito = "REVISAR"
        aprovado = False

    # Prioriza ações das personas vetadoras, depois menor nota (< 8.0)
    prioritized_personas = [
        *[p for p in ordered if p.persona_id in personas_vetadoras],
        *sorted(
            (p for p in ordered if p.persona_id not in personas_vetadoras and p.nota < APPROVAL_MEAN_THRESHOLD),
            key=lambda p: p.nota,
        ),
    ]
    plano_acao: list[str] = []
    seen_actions: set[str] = set()
    for persona in prioritized_personas:
        for action in persona.acoes_corretivas:
            cleaned = action.strip()
            if cleaned and cleaned not in seen_actions:
                seen_actions.add(cleaned)
                plano_acao.append(f"[{persona.persona_nome}] {cleaned}")
            if len(plano_acao) >= 8:
                break
        if len(plano_acao) >= 8:
            break

    if veredito == "APROVADO":
        resumo_executivo = (
            f"APROVADO pelo comitê ({media_geral:.2f}/10 >= {APPROVAL_MEAN_THRESHOLD:.1f}), "
            f"sem vetos críticos e rotina {schedule_fit.classificacao_exibicao}."
        )
    elif veredito == "VETADO":
        veto_nomes = ", ".join(_PERSONA_LABELS[p] for p in personas_vetadoras)
        resumo_executivo = (
            f"VETADO automaticamente por {veto_nomes} (nota < {CRITICAL_VETO_THRESHOLD:.1f}) "
            f"apesar de média {media_geral:.2f}/10. Rotina: {schedule_fit.classificacao_exibicao}."
        )
    else:
        resumo_executivo = (
            f"REVISÃO RECOMENDADA: média {media_geral:.2f}/10 abaixo do corte {APPROVAL_MEAN_THRESHOLD:.1f}, "
            f"sem vetos eliminatórios. Rotina: {schedule_fit.classificacao_exibicao}."
        )

    return CommitteeEvaluationResult(
        vaga_alvo=vaga_alvo,
        veredito=veredito,
        aprovado=aprovado,
        media_geral=media_geral,
        limiar_aprovacao=APPROVAL_MEAN_THRESHOLD,
        limiar_veto_critico=CRITICAL_VETO_THRESHOLD,
        veto=veto,
        avaliacoes=ordered,
        compatibilidade_horario=schedule_fit,
        plano_acao_prioritario=plano_acao,
        modo_avaliacao=modo_avaliacao,
        resumo_executivo=resumo_executivo,
    )


def build_committee_prompt(
    resume_markdown: str,
    job_data: dict[str, Any],
    profile: CandidateProfile,
    schedule_fit: ScheduleFitResult,
) -> str:
    """Monta prompt estruturado para avaliação via LLM com Structured Outputs (7 personas)."""
    janela = profile.horario_trabalho_desejado.janela_disponivel.get(
        "segunda_a_sexta", "19:00 - 00:00 (BRT)"
    )
    return (
        "Você é a Banca Examinadora Cognitiva de Contratação (The 7 Personas Hiring Board).\n"
        "Avalie o currículo em Markdown frente à vaga alvo e às restrições de rotina noturna/assíncrona do candidato.\n\n"
        f"Restrição de Rotina do Candidato: {profile.horario_trabalho_desejado.tipo_rotina} | "
        f"Janela: {janela} | Permite reuniões em horário comercial: "
        f"{profile.horario_trabalho_desejado.permite_reunioes_horario_comercial}\n"
        f"Classificação prévia de horário: {schedule_fit.classificacao_exibicao} "
        f"({schedule_fit.score_horario}/100) — Red flags: {', '.join(schedule_fit.red_flags) or 'nenhum'}\n\n"
        "Personas obrigatórias (retornar exatamente 1 avaliação para cada persona_id abaixo, nota 0.0 a 10.0):\n"
        "1. ats_screener (ATS Screener): Densidade de keywords técnicas e legibilidade de parser.\n"
        "2. tech_recruiter (Tech Recruiter): Clareza visual, senioridade e regra dos 6 segundos.\n"
        "3. engineering_manager (Engineering Manager): Arquitetura, concorrência e profundidade técnica.\n"
        "4. senior_peer (Senior Peer Developer): Qualidade de código, testes automatizados e CI/CD.\n"
        "5. product_manager (Product Manager): Métricas de negócio (Google XYZ) e foco em entrega de valor.\n"
        "6. cto_head (CTO / Head): Governança, escalabilidade e maturidade técnica.\n"
        "7. skeptic_recruiter (Recrutador Cético): Caçador de clichês, contradições e inconsistências de rotina.\n\n"
        f"VAGA ALVO: {job_data.get('titulo', 'Software Engineer')} @ {job_data.get('empresa', 'Empresa')}\n"
        f"Localização: {job_data.get('localizacao', 'Remote')} | Contrato: {job_data.get('tipo_contrato', 'Remote')}\n"
        f"Descrição da Vaga:\n{job_data.get('descricao', job_data.get('resumo', ''))}\n\n"
        f"CURRÍCULO EM MARKDOWN:\n{resume_markdown}\n"
    )


def create_gemini_committee_provider(
    model: str = "gemini-2.5-flash",
    api_key: str | None = None,
) -> CommitteeLLMProvider:
    """
    Cria provedor opcional via Google GenAI SDK com Structured Outputs (Pydantic).
    Importação lazy para manter inicialização e testes 100% offline.
    """
    resolved_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not resolved_key:
        raise ValueError(
            "Chave de API Gemini ausente. Defina GEMINI_API_KEY ou informe api_key."
        )

    def _provider(prompt: str, schema_cls: type[CommitteePersonaBatch]) -> CommitteePersonaBatch:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=resolved_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema_cls,
                temperature=0.2,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema_cls):
            return parsed
        return schema_cls.model_validate_json(response.text)

    return _provider


def evaluate_application_committee(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any],
    resume_markdown: str | None = None,
    llm_provider: CommitteeLLMProvider | None = None,
) -> dict[str, Any]:
    """
    Executa a Banca Examinadora Cognitiva das 7 Personas sobre um pacote vaga + currículo.
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    titulo_vaga = str(job_data.get("titulo") or "Software Engineer")
    empresa = str(job_data.get("empresa") or "Target Company")
    vaga_alvo = f"{titulo_vaga} ({empresa})"

    if resume_markdown is None:
        calibrated = calibrate_resume_for_job(profile, job_data)
        resume_md = calibrated["curriculo_markdown"]
    else:
        resume_md = resume_markdown

    desc_vaga = str(job_data.get("descricao") or job_data.get("resumo") or "")
    schedule_dict = evaluate_schedule_fit(
        f"{titulo_vaga} {desc_vaga}",
        str(job_data.get("localizacao") or "Worldwide"),
        str(job_data.get("tipo_contrato") or "Remote"),
        profile.horario_trabalho_desejado,
    )
    schedule_fit = ScheduleFitResult.model_validate(schedule_dict)

    if llm_provider is not None:
        prompt = build_committee_prompt(resume_md, job_data, profile, schedule_fit)
        batch = llm_provider(prompt, CommitteePersonaBatch)
        result = compute_committee_consensus(
            batch.avaliacoes,
            schedule_fit=schedule_fit,
            vaga_alvo=vaga_alvo,
            modo_avaliacao="llm_estruturado",
        )
        return result.model_dump()

    career_diagnosis = analyze_career_profile(profile)
    gap_report = detect_job_gaps(profile, job_data)

    avaliacoes = [
        _evaluate_ats_screener(resume_md, job_data),
        _evaluate_tech_recruiter(resume_md, job_data, career_diagnosis),
        _evaluate_engineering_manager(resume_md, gap_report),
        _evaluate_senior_peer(resume_md),
        _evaluate_product_manager(resume_md),
        _evaluate_cto_head(resume_md, career_diagnosis),
        _evaluate_skeptic_recruiter(resume_md, job_data, profile, schedule_fit),
    ]

    result = compute_committee_consensus(
        avaliacoes,
        schedule_fit=schedule_fit,
        vaga_alvo=vaga_alvo,
        modo_avaliacao="heuristico_deterministico",
    )
    return result.model_dump()
