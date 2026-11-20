#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor MCP Nativo do Career Copilot.
Permite que Claude, Antigravity, Cursor ou Codex consumam as ferramentas de carreira.
"""

from __future__ import annotations

import json
import sys
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("career-copilot")
except Exception:
    try:
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("career-copilot")
    except Exception:
        mcp = None

from .config import atomic_write_json, get_vagas_db_path, load_profile
from .copiloto import prepare_assisted_application
from .evaluators import evaluate_application_committee
from .miners import mine_all_opportunities
from .profiler import analyze_career_profile, detect_job_gaps
from .tailor import (
    calibrate_resume_for_job,
    compile_resume_to_pdf,
    generate_cover_pitch,
)


def _load_job_by_id(job_id: str) -> tuple[dict[str, Any] | None, str | None]:
    vagas_db = get_vagas_db_path()
    if not vagas_db.exists():
        return None, "Base de vagas vazia. Execute mine_jobs primeiro."
    with open(vagas_db, "r", encoding="utf-8") as f:
        vagas = json.load(f)
    vaga = next((v for v in vagas if v.get("id") == job_id), None)
    if not vaga:
        return None, f"Vaga com id '{job_id}' não encontrada."
    return vaga, None


if mcp:

    @mcp.tool()
    def get_career_profile() -> str:
        """
        Retorna o diagnóstico de carreira do profissional, senioridade estimada e
        viabilidade da rotina/horário de trabalho desejado.
        """
        try:
            profile = load_profile()
            res = analyze_career_profile(profile)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def mine_jobs(
        modo: str = "todos",
        min_schedule: int = 50,
        min_stack: int = 25,
        fontes: list[str] | None = None,
        use_cache: bool = True,
    ) -> str:
        """
        Minera vagas ativas (internacionais e nacionais) cruzando com as preferências
        horárias e a stack do candidato. Modos: 'todos', 'internacional', 'nacional'.
        """
        try:
            profile = load_profile()
            vagas = mine_all_opportunities(
                profile,
                modo=modo,
                min_schedule=min_schedule,
                min_stack=min_stack,
                fontes=fontes,
                use_cache=use_cache,
            )

            vagas_db = get_vagas_db_path()
            atomic_write_json(vagas_db, vagas)

            resumo = [
                {
                    "id": v["id"],
                    "titulo": v["titulo"],
                    "empresa": v["empresa"],
                    "fonte": v["fonte"],
                    "origem": v["origem"],
                    "localizacao": v["localizacao"],
                    "score_composto": v["score_composto"],
                    "horario_status": v["schedule_fit"]["status"],
                    "horario_classificacao": v["schedule_fit"].get(
                        "classificacao_exibicao", f"[{v['schedule_fit']['status']}]"
                    ),
                    "horario_score": v["schedule_fit"]["score_horario"],
                    "stack_score": v["stack_score"],
                    "url": v["url"],
                }
                for v in vagas[:15]
            ]
            return json.dumps(
                {"total_encontradas": len(vagas), "top_15": resumo},
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def evaluate_job(
        job_description: str,
        job_location: str = "Worldwide",
        job_type: str = "Remote",
    ) -> str:
        """
        Avalia detalhadamente se uma vaga avulsa é compatível com o perfil e a janela
        de horário de trabalho desejada pelo candidato.
        """
        try:
            profile = load_profile()
            mock_job = {
                "titulo": "Vaga Analisada",
                "empresa": "Empresa",
                "origem": "Personalizada",
                "descricao": job_description,
                "localizacao": job_location,
                "tipo_contrato": job_type,
            }
            res = detect_job_gaps(profile, mock_job)
            res["horario_classificacao"] = res["compatibilidade_horario"].get(
                "classificacao_exibicao",
                f"[{res['compatibilidade_horario']['status']}]",
            )
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def tailor_application(job_id: str) -> str:
        """
        Gera o pacote de candidatura sob medida (Currículo adaptado em Markdown +
        Cold Pitch em inglês e português) para uma vaga minerada.
        """
        try:
            profile = load_profile()
            vaga, err = _load_job_by_id(job_id)
            if err or not vaga:
                return json.dumps({"erro": err}, ensure_ascii=False)

            cv_res = calibrate_resume_for_job(profile, vaga)
            pitch_res = generate_cover_pitch(profile, vaga)

            return json.dumps(
                {
                    "vaga": cv_res["vaga_alvo"],
                    "curriculo_markdown": cv_res["curriculo_markdown"],
                    "cold_pitch_ingles": pitch_res["pitch_ingles"],
                    "cold_pitch_portugues": pitch_res["pitch_portugues"],
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def review_application(
        job_id: str | None = None,
        job_description: str | None = None,
        job_title: str = "Vaga Analisada",
        job_company: str = "Empresa",
        job_location: str = "Worldwide",
        job_type: str = "Remote",
        resume_markdown: str | None = None,
    ) -> str:
        """
        Avalia currículo e candidatura com a Banca Examinadora Cognitiva (7 Personas):
        ATS Screener, Tech Recruiter, Engineering Manager, Senior Peer, Product Manager,
        CTO/Head e Recrutador Cético, aplicando consenso >= 8.0 e veto automático (< 7.0 em ATS/Cético).
        """
        try:
            profile = load_profile()
            if job_id:
                vaga, err = _load_job_by_id(job_id)
                if err or not vaga:
                    return json.dumps({"erro": err}, ensure_ascii=False)
            elif job_description:
                vaga = {
                    "titulo": job_title,
                    "empresa": job_company,
                    "origem": "Personalizada",
                    "descricao": job_description,
                    "localizacao": job_location,
                    "tipo_contrato": job_type,
                }
            else:
                return json.dumps(
                    {"erro": "Informe 'job_id' ou 'job_description' para avaliação da banca."},
                    ensure_ascii=False,
                )

            res = evaluate_application_committee(
                profile,
                vaga,
                resume_markdown=resume_markdown,
            )
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def export_resume_pdf(
        job_id: str | None = None,
        job_title: str = "Software Engineer",
        job_company: str = "Target Company",
        resume_markdown: str | None = None,
        output_path: str | None = None,
        save_html: bool = False,
        load_web_fonts: bool = True,
    ) -> str:
        """
        Compila o currículo customizado em PDF A4 corporativo (Playwright Chromium headless)
        com tipografia Inter/JetBrains Mono, metadados corporativos e validação de leitura ATS.
        """
        try:
            profile = load_profile()
            if job_id:
                vaga, err = _load_job_by_id(job_id)
                if err or not vaga:
                    return json.dumps({"erro": err}, ensure_ascii=False)
            else:
                vaga = {
                    "titulo": job_title,
                    "empresa": job_company,
                }

            res = compile_resume_to_pdf(
                profile,
                vaga,
                resume_markdown=resume_markdown,
                output_path=output_path,
                save_html=save_html,
                load_web_fonts=load_web_fonts,
            )
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def assist_application(
        job_id: str | None = None,
        job_url: str | None = None,
        job_title: str = "Software Engineer",
        job_company: str = "Target Company",
        job_description: str = "",
        job_location: str = "Worldwide",
        job_type: str = "Remote",
        pdf_path: str | None = None,
        dry_run: bool = True,
        allow_schedule_conflict: bool = False,
        load_web_fonts: bool = True,
        custom_answers: dict[str, str] | None = None,
    ) -> str:
        """
        Copiloto Human-in-the-Loop via Playwright: valida conflito de horário, prepara
        PDF A4 e respostas de triagem, abre navegador persistente pré-autenticado, preenche
        formulário e PAUSA antes do envio humano (nunca submete automaticamente).
        """
        try:
            profile = load_profile()
            if job_id:
                vaga, err = _load_job_by_id(job_id)
                if err or not vaga:
                    return json.dumps({"erro": err}, ensure_ascii=False)
                if job_url:
                    vaga = {**vaga, "url": job_url}
            elif job_url:
                vaga = {
                    "titulo": job_title,
                    "empresa": job_company,
                    "url": job_url,
                    "descricao": job_description,
                    "localizacao": job_location,
                    "tipo_contrato": job_type,
                }
            else:
                return json.dumps(
                    {"erro": "Informe 'job_id' ou 'job_url' para preparar a candidatura assistida."},
                    ensure_ascii=False,
                )

            res = prepare_assisted_application(
                profile,
                vaga,
                pdf_path=pdf_path,
                custom_answers=custom_answers,
                load_web_fonts=load_web_fonts,
                dry_run=dry_run,
                allow_schedule_conflict=allow_schedule_conflict,
                wait_for_human=not dry_run,
            )
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)


def run_server() -> None:
    if mcp:
        mcp.run(transport="stdio")
    else:
        print("Módulo MCP não disponível no ambiente.", file=sys.stderr)


if __name__ == "__main__":
    run_server()
