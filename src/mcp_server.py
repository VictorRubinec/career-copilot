#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor MCP Nativo do Career Copilot
Permite que Claude, Antigravity, Cursor ou Codex consumam as ferramentas de carreira.
"""

import json
from pathlib import Path

try:
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer("career-copilot")
except Exception:
    try:
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("career-copilot")
    except Exception:
        mcp = None

from .config import load_profile, VAGAS_DB_PATH
from .profiler import analyze_career_profile, detect_job_gaps
from .miners import mine_all_opportunities
from .tailor import calibrate_resume_for_job, generate_cover_pitch
from .evaluators.schedule_matcher import evaluate_schedule_fit


if mcp:
    @mcp.tool()
    def get_career_profile() -> str:
        """
        Retorna o diagnóstico de carreira do profissional, senioridade estimada e viabilidade da rotina/horário de trabalho desejado.
        """
        profile = load_profile()
        res = analyze_career_profile(profile)
        return json.dumps(res, ensure_ascii=False, indent=2)


    @mcp.tool()
    def mine_jobs(modo: str = "todos", min_schedule: int = 50, min_stack: int = 25) -> str:
        """
        Minera vagas ativas (internacionais e nacionais) cruzando com as preferências horárias e a stack do candidato.
        Modos disponíveis: 'todos', 'internacional', 'nacional'.
        """
        profile = load_profile()
        vagas = mine_all_opportunities(profile, modo=modo, min_schedule=min_schedule, min_stack=min_stack)
        
        VAGAS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(VAGAS_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(vagas, f, ensure_ascii=False, indent=2)

        resumo = [
            {
                "id": v["id"],
                "titulo": v["titulo"],
                "empresa": v["empresa"],
                "origem": v["origem"],
                "localizacao": v["localizacao"],
                "score_composto": v["score_composto"],
                "horario_status": v["schedule_fit"]["status"],
                "horario_score": v["schedule_fit"]["score_horario"],
                "stack_score": v["stack_score"],
                "url": v["url"]
            }
            for v in vagas[:15]
        ]
        return json.dumps({"total_encontradas": len(vagas), "top_15": resumo}, ensure_ascii=False, indent=2)


    @mcp.tool()
    def evaluate_job(job_description: str, job_location: str = "Worldwide", job_type: str = "Remote") -> str:
        """
        Avalia detalhadamente se uma vaga avulsa é compatível com o perfil e a janela de horário de trabalho desejada pelo candidato.
        """
        profile = load_profile()
        mock_job = {
            "titulo": "Vaga Analisada",
            "empresa": "Empresa",
            "origem": "Personalizada",
            "descricao": job_description,
            "localizacao": job_location,
            "tipo_contrato": job_type
        }
        res = detect_job_gaps(profile, mock_job)
        return json.dumps(res, ensure_ascii=False, indent=2)


    @mcp.tool()
    def tailor_application(job_id: str) -> str:
        """
        Gera o pacote de candidatura sob medida (Currículo adaptado em Markdown + Cold Pitch em inglês e português) para uma vaga minerada.
        """
        profile = load_profile()
        if not VAGAS_DB_PATH.exists():
            return json.dumps({"erro": "Base de vagas vazia. Execute mine_jobs primeiro."}, ensure_ascii=False)

        with open(VAGAS_DB_PATH, "r", encoding="utf-8") as f:
            vagas = json.load(f)

        vaga = next((v for v in vagas if v.get("id") == job_id), None)
        if not vaga:
            return json.dumps({"erro": f"Vaga com id '{job_id}' não encontrada."}, ensure_ascii=False)

        cv_res = calibrate_resume_for_job(profile, vaga)
        pitch_res = generate_cover_pitch(profile, vaga)

        return json.dumps({
            "vaga": cv_res["vaga_alvo"],
            "curriculo_markdown": cv_res["curriculo_markdown"],
            "cold_pitch_ingles": pitch_res["pitch_ingles"],
            "cold_pitch_portugues": pitch_res["pitch_portugues"]
        }, ensure_ascii=False, indent=2)


def run_server():
    if mcp:
        mcp.run(transport="stdio")
    else:
        print("Módulo MCP não disponível no ambiente.", file=sys.stderr)


if __name__ == "__main__":
    run_server()
