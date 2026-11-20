"""Copiloto Human-in-the-Loop via Playwright com navegador pré-autenticado e pausa humana."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from ..config import get_browser_profile_dir, get_logger
from ..evaluators.schedule_matcher import evaluate_schedule_fit
from ..models import (
    ApplicationPayload,
    CandidateProfile,
    CopilotSessionResult,
    FilledFieldReport,
    ScheduleFitResult,
)
from ..tailor.pdf_compiler import compile_resume_to_pdf
from .form_mapper import (
    FIELD_SELECTOR_RULES,
    SCREENING_TEXTAREA_RULES,
    build_application_payload,
    detect_external_gate,
    has_prior_application_for_url,
    record_application_draft,
)

logger = get_logger(__name__)

PauseCallback = Callable[[Any, CopilotSessionResult], None]

HITL_SECURITY_NOTICE = (
    "SEGURANÇA HUMAN-IN-THE-LOOP: O Career Copilot nunca envia ou submete candidaturas "
    "automaticamente. Revise os campos preenchidos e clique manualmente em Enviar/Submit."
)


class HumanInTheLoopCopilot:
    """
    Assistente de preenchimento em navegador persistente Playwright.
    Preenche dados básicos, upload de PDF e triagem, pausando para revisão e envio humano.
    """

    def __init__(
        self,
        profile_dir: Path | None = None,
        headless: bool = False,
        timeout_ms: int = 20000,
        wait_timeout_ms: int = 300000,
    ) -> None:
        self.profile_dir = (
            profile_dir if profile_dir is not None else get_browser_profile_dir()
        )
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.wait_timeout_ms = wait_timeout_ms

    @staticmethod
    def _value_for_field(payload: ApplicationPayload, field_name: str) -> str:
        mapping = {
            "first_name": payload.primeiro_nome,
            "last_name": payload.sobrenome,
            "full_name": payload.nome_completo,
            "email": payload.email,
            "phone": payload.telefone,
            "linkedin": payload.linkedin,
            "github": payload.github,
            "portfolio": payload.portfolio,
            "location": payload.localizacao,
            "cover_letter": payload.carta_apresentacao,
            "resume_pdf": payload.curriculo_pdf_path or "",
        }
        return mapping.get(field_name, "")

    @staticmethod
    def _describe_element_context(page: Any, element: Any) -> str:
        try:
            ctx = element.evaluate(
                """(el) => {
                    const id = el.id || '';
                    const lbl = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                    const wrapLbl = el.closest('label');
                    return [
                        el.name || '',
                        id,
                        el.getAttribute('placeholder') || '',
                        el.getAttribute('aria-label') || '',
                        lbl ? lbl.textContent : '',
                        wrapLbl ? wrapLbl.textContent : ''
                    ].join(' ');
                }"""
            )
            return str(ctx or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _mark_filled(element: Any) -> None:
        try:
            element.evaluate("(el) => { el.dataset.careerCopilotFilled = '1'; }")
        except Exception:
            pass

    def _fill_form_on_page(
        self,
        page: Any,
        payload: ApplicationPayload,
    ) -> tuple[list[FilledFieldReport], list[str]]:
        reports: list[FilledFieldReport] = []
        filled_split_name = False

        for field_name, field_type, selectors in FIELD_SELECTOR_RULES:
            if field_name == "full_name" and filled_split_name:
                continue

            value = self._value_for_field(payload, field_name)
            if not value:
                continue

            if field_type == "file" and not Path(value).exists():
                reports.append(
                    FilledFieldReport(
                        campo_logico=field_name,
                        seletor=selectors[0],
                        tipo=field_type,
                        preenchido=False,
                        motivo_ignorado="Arquivo PDF não encontrado em disco.",
                    )
                )
                continue

            matched = False
            for selector in selectors:
                locator = page.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                if count <= 0:
                    continue

                candidate = locator.first
                try:
                    already_marked = candidate.evaluate(
                        "(el) => el.dataset.careerCopilotFilled === '1'"
                    )
                    if already_marked:
                        continue
                except Exception:
                    pass

                if field_type == "file":
                    try:
                        candidate.set_input_files(value)
                        self._mark_filled(candidate)
                        reports.append(
                            FilledFieldReport(
                                campo_logico=field_name,
                                seletor=selector,
                                tipo=field_type,
                                preenchido=True,
                                valor_preview=Path(value).name,
                            )
                        )
                        matched = True
                        break
                    except Exception as exc:
                        logger.warning("Falha ao anexar PDF em %s: %s", selector, exc)
                        continue

                try:
                    if not candidate.is_visible():
                        continue
                    current_val = (candidate.input_value() or "").strip()
                    if current_val:
                        reports.append(
                            FilledFieldReport(
                                campo_logico=field_name,
                                seletor=selector,
                                tipo=field_type,
                                preenchido=False,
                                motivo_ignorado="Campo já preenchido previamente no formulário.",
                            )
                        )
                        matched = True
                        break
                    candidate.fill(value)
                    self._mark_filled(candidate)
                    if field_name in ("first_name", "last_name"):
                        filled_split_name = True
                    preview = value[:80] + ("..." if len(value) > 80 else "")
                    reports.append(
                        FilledFieldReport(
                            campo_logico=field_name,
                            seletor=selector,
                            tipo=field_type,
                            preenchido=True,
                            valor_preview=preview,
                        )
                    )
                    matched = True
                    break
                except Exception as exc:
                    logger.warning("Falha ao preencher %s (%s): %s", field_name, selector, exc)

            if not matched:
                logger.debug("Seletor não encontrado na página para '%s'.", field_name)

        # Preenche textareas de triagem que não foram cobertas por cover_letter
        textareas = page.locator("textarea")
        try:
            ta_count = textareas.count()
        except Exception:
            ta_count = 0

        for idx in range(ta_count):
            ta = textareas.nth(idx)
            try:
                if ta.evaluate("(el) => el.dataset.careerCopilotFilled === '1'"):
                    continue
                if not ta.is_visible() or (ta.input_value() or "").strip():
                    continue
                ctx = self._describe_element_context(page, ta)
                for keywords, answer_key in SCREENING_TEXTAREA_RULES:
                    if any(kw in ctx for kw in keywords):
                        answer = payload.respostas_triagem.get(answer_key, "")
                        if answer:
                            ta.fill(answer)
                            self._mark_filled(ta)
                            reports.append(
                                FilledFieldReport(
                                    campo_logico=f"triagem:{answer_key}",
                                    seletor=f"textarea#{idx}",
                                    tipo="textarea",
                                    preenchido=True,
                                    valor_preview=answer[:80] + ("..." if len(answer) > 80 else ""),
                                )
                            )
                        break
            except Exception:
                continue

        # Identifica campos obrigatórios que ainda exigem revisão/decisão humana
        pending_human: list[str] = []
        try:
            pending_raw = page.evaluate(
                """() => {
                    const out = [];
                    const els = document.querySelectorAll('input[required], textarea[required], select[required]');
                    for (const el of els) {
                        const type = (el.getAttribute('type') || '').toLowerCase();
                        if (type === 'hidden' || type === 'submit' || type === 'button') continue;
                        let empty = false;
                        if (type === 'file') {
                            empty = !el.files || el.files.length === 0;
                        } else if (type === 'checkbox' || type === 'radio') {
                            empty = !el.checked;
                        } else {
                            empty = !(el.value || '').trim();
                        }
                        if (empty) {
                            const label = el.getAttribute('aria-label') || el.name || el.id || el.tagName.toLowerCase();
                            out.push(label);
                        }
                    }
                    return out;
                }"""
            )
            if isinstance(pending_raw, list):
                pending_human = [str(x) for x in pending_raw if str(x).strip()]
        except Exception:
            pass

        return reports, pending_human

    @staticmethod
    def _inject_human_review_banner(page: Any, vaga_alvo: str) -> None:
        try:
            page.evaluate(
                """(vaga) => {
                    if (document.getElementById('career-copilot-hitl-banner')) return;
                    const div = document.createElement('div');
                    div.id = 'career-copilot-hitl-banner';
                    div.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#0f172a;color:#f8fafc;padding:10px 16px;font:600 13px/1.4 system-ui,sans-serif;border-bottom:3px solid #3b82f6;box-shadow:0 4px 12px rgba(0,0,0,0.2);';
                    div.textContent = `Career Copilot (Human-in-the-Loop): Campos preenchidos para ${vaga}. Revise atentamente e clique manualmente em Enviar/Submit.`;
                    document.body.prepend(div);
                }""",
                vaga_alvo,
            )
        except Exception:
            pass

    def _run_session_sync(
        self,
        payload: ApplicationPayload,
        schedule_fit: ScheduleFitResult,
        duplicata_detectada: bool,
        wait_for_human: bool,
        pause_callback: PauseCallback | None,
    ) -> CopilotSessionResult:
        from playwright.sync_api import sync_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        vaga_alvo = f"{payload.vaga_titulo} ({payload.empresa})"

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(self.timeout_ms)
                page.goto(payload.url_candidatura, wait_until="domcontentloaded")

                gate = detect_external_gate(page.url, page.content())
                if gate:
                    result = CopilotSessionResult(
                        status="PAUSADO_VERIFICACAO_HUMANA",
                        vaga_alvo=vaga_alvo,
                        url_destino=payload.url_candidatura,
                        submetido_automaticamente=False,
                        requer_confirmacao_humana=True,
                        perfil_navegador=str(self.profile_dir),
                        curriculo_pdf_path=payload.curriculo_pdf_path,
                        compatibilidade_horario=schedule_fit,
                        bloqueio_externo_detectado=gate,
                        duplicata_detectada=duplicata_detectada,
                        aviso_seguranca=HITL_SECURITY_NOTICE,
                        proximos_passos_humano=[
                            gate,
                            "Após concluir a verificação no navegador, revise os campos e submeta manualmente.",
                        ],
                    )
                    if pause_callback is not None:
                        pause_callback(page, result)
                    elif wait_for_human:
                        try:
                            page.wait_for_event("close", timeout=self.wait_timeout_ms)
                        except Exception:
                            pass
                    return result

                filled_reports, pending_human = self._fill_form_on_page(page, payload)
                self._inject_human_review_banner(page, vaga_alvo)

                next_steps = [
                    "Conferir dados pessoais, links e respostas de triagem assíncrona no navegador.",
                    "Confirmar que o currículo PDF A4 foi anexado corretamente.",
                    "Preencher eventuais campos obrigatórios pendentes e clicar manualmente em Submit/Enviar.",
                ]
                result = CopilotSessionResult(
                    status="AGUARDANDO_REVISAO_HUMANA",
                    vaga_alvo=vaga_alvo,
                    url_destino=payload.url_candidatura,
                    submetido_automaticamente=False,
                    requer_confirmacao_humana=True,
                    perfil_navegador=str(self.profile_dir),
                    curriculo_pdf_path=payload.curriculo_pdf_path,
                    compatibilidade_horario=schedule_fit,
                    campos_preenchidos=filled_reports,
                    campos_pendentes_humano=pending_human,
                    duplicata_detectada=duplicata_detectada,
                    aviso_seguranca=HITL_SECURITY_NOTICE,
                    proximos_passos_humano=next_steps,
                )

                if pause_callback is not None:
                    pause_callback(page, result)
                elif wait_for_human:
                    try:
                        page.wait_for_event("close", timeout=self.wait_timeout_ms)
                    except Exception:
                        pass
                return result
            finally:
                context.close()

    def run_session(
        self,
        payload: ApplicationPayload,
        schedule_fit: ScheduleFitResult,
        duplicata_detectada: bool = False,
        wait_for_human: bool = True,
        pause_callback: PauseCallback | None = None,
    ) -> CopilotSessionResult:
        """Executa sessão Playwright persistente com offload automático se houver loop asyncio."""
        try:
            asyncio.get_running_loop()
            in_running_loop = True
        except RuntimeError:
            in_running_loop = False

        if not in_running_loop:
            return self._run_session_sync(
                payload,
                schedule_fit,
                duplicata_detectada,
                wait_for_human,
                pause_callback,
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(
                self._run_session_sync,
                payload,
                schedule_fit,
                duplicata_detectada,
                wait_for_human,
                pause_callback,
            ).result()


def prepare_assisted_application(
    profile_data: dict[str, Any] | CandidateProfile,
    job_data: dict[str, Any],
    pdf_path: str | Path | None = None,
    resume_markdown: str | None = None,
    custom_answers: dict[str, str] | None = None,
    auto_compile_pdf: bool = True,
    load_web_fonts: bool = True,
    dry_run: bool = False,
    allow_schedule_conflict: bool = False,
    wait_for_human: bool = True,
    headless: bool = False,
    profile_dir: str | Path | None = None,
    pause_callback: PauseCallback | None = None,
) -> dict[str, Any]:
    """
    Orquestra preparação e preenchimento assistido (Human-in-the-Loop):
    1. Valida conflito de horário diurno (bloqueando vagas INCOMPATÍVEIS por padrão).
    2. Compila currículo PDF A4 corporativo se nenhum PDF prévio for fornecido.
    3. Prepara payload de triagem e carta de apresentação.
    4. Abre navegador persistente pré-autenticado, preenche campos e pausa antes do envio.
    """
    profile = (
        profile_data
        if isinstance(profile_data, CandidateProfile)
        else CandidateProfile.model_validate(profile_data)
    )

    titulo = str(job_data.get("titulo") or "Software Engineer")
    empresa = str(job_data.get("empresa") or "Target Company")
    vaga_alvo = f"{titulo} ({empresa})"
    url = str(job_data.get("url") or "").strip()
    desc = str(job_data.get("descricao") or job_data.get("resumo") or "")

    schedule_dict = evaluate_schedule_fit(
        f"{titulo} {desc}",
        str(job_data.get("localizacao") or "Worldwide"),
        str(job_data.get("tipo_contrato") or "Remote"),
        profile.horario_trabalho_desejado,
    )
    schedule_fit = ScheduleFitResult.model_validate(schedule_dict)
    resolved_profile_dir = (
        Path(profile_dir) if profile_dir is not None else get_browser_profile_dir()
    )
    duplicata = has_prior_application_for_url(url)

    if schedule_fit.status == "INCOMPATIVEL" and not allow_schedule_conflict:
        blocked = CopilotSessionResult(
            status="BLOQUEADO_CONFLITO_HORARIO",
            vaga_alvo=vaga_alvo,
            url_destino=url,
            submetido_automaticamente=False,
            requer_confirmacao_humana=True,
            perfil_navegador=str(resolved_profile_dir),
            curriculo_pdf_path=str(pdf_path) if pdf_path else None,
            compatibilidade_horario=schedule_fit,
            duplicata_detectada=duplicata,
            aviso_seguranca=HITL_SECURITY_NOTICE,
            proximos_passos_humano=[
                f"Vaga bloqueada pelo filtro anti-conflito: {', '.join(schedule_fit.red_flags) or schedule_fit.justificativa}",
                "Use --allow-conflict (CLI) ou allow_schedule_conflict=True (MCP/API) apenas se desejar forçar a abertura.",
            ],
        )
        return blocked.model_dump()

    if not url:
        err_result = CopilotSessionResult(
            status="ERRO",
            vaga_alvo=vaga_alvo,
            url_destino="",
            submetido_automaticamente=False,
            requer_confirmacao_humana=True,
            perfil_navegador=str(resolved_profile_dir),
            curriculo_pdf_path=str(pdf_path) if pdf_path else None,
            compatibilidade_horario=schedule_fit,
            duplicata_detectada=False,
            aviso_seguranca=HITL_SECURITY_NOTICE,
            proximos_passos_humano=["Forneça uma URL de candidatura válida para abrir o copiloto."],
        )
        return err_result.model_dump()

    resolved_pdf: str | None = str(pdf_path) if pdf_path is not None else None
    if resolved_pdf is None and auto_compile_pdf:
        compiled = compile_resume_to_pdf(
            profile,
            job_data,
            resume_markdown=resume_markdown,
            load_web_fonts=load_web_fonts,
        )
        resolved_pdf = compiled["pdf_path"]

    payload = build_application_payload(
        profile,
        job_data,
        pdf_path=resolved_pdf,
        custom_answers=custom_answers,
    )

    if dry_run:
        draft_fields = [
            FilledFieldReport(
                campo_logico=key,
                seletor="dry-run",
                tipo="file" if key == "curriculo_pdf_path" else "text",
                preenchido=bool(val),
                valor_preview=str(val)[:80],
            )
            for key, val in (
                ("nome_completo", payload.nome_completo),
                ("email", payload.email),
                ("telefone", payload.telefone),
                ("linkedin", payload.linkedin),
                ("github", payload.github),
                ("curriculo_pdf_path", payload.curriculo_pdf_path or ""),
            )
            if val
        ]
        dry_result = CopilotSessionResult(
            status="DRY_RUN_PREPARADO",
            vaga_alvo=vaga_alvo,
            url_destino=url,
            submetido_automaticamente=False,
            requer_confirmacao_humana=True,
            perfil_navegador=str(resolved_profile_dir),
            curriculo_pdf_path=resolved_pdf,
            compatibilidade_horario=schedule_fit,
            campos_preenchidos=draft_fields,
            duplicata_detectada=duplicata,
            aviso_seguranca=HITL_SECURITY_NOTICE,
            proximos_passos_humano=[
                "Dry-run concluído: PDF compilado e respostas preparadas sem abrir navegador.",
                "Execute sem --dry-run para preencher o formulário no navegador persistente.",
            ],
        )
        record_application_draft(dry_result, payload)
        return dry_result.model_dump()

    copilot = HumanInTheLoopCopilot(
        profile_dir=resolved_profile_dir,
        headless=headless,
    )
    session_result = copilot.run_session(
        payload=payload,
        schedule_fit=schedule_fit,
        duplicata_detectada=duplicata,
        wait_for_human=wait_for_human,
        pause_callback=pause_callback,
    )
    record_application_draft(session_result, payload)
    return session_result.model_dump()
