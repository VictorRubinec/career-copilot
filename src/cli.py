#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Principal do Career Copilot
"""

import sys
import json
import argparse
from pathlib import Path

from .config import load_profile, VAGAS_DB_PATH
from .profiler import analyze_career_profile, detect_job_gaps
from .miners import mine_all_opportunities
from .tailor import calibrate_resume_for_job, generate_cover_pitch


def cmd_profile(args):
    profile = load_profile()
    res = analyze_career_profile(profile)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("\n=======================================================")
        print("         DIAGNÓSTICO DE CARREIRA E PERFIL")
        print("=======================================================")
        print(f"Candidato: {res['candidato']['nome']} ({res['candidato']['titulo']})")
        print(f"Localização: {res['candidato']['localizacao']}")
        print(f"Senioridade Estimada: {res['diagnostico_carreira']['senioridade_estimada']}")
        print(f"Nível de Autonomia: {res['diagnostico_carreira']['nivel_autonomia']}")
        print(f"Índice de Prontidão Internacional: {res['diagnostico_carreira']['readiness_internacional_score']}/100")
        print("\n--- Análise de Horário e Rotina Desejada ---")
        print(f"Status de Viabilidade: {res['analise_horario_trabalho']['status']}")
        print(f"Janela Declarada: {res['analise_horario_trabalho']['janela_declarada']}")
        print(f"Carga Alvo: {res['analise_horario_trabalho']['carga_alvo']}")
        print(f"Regime Recomendado: {res['analise_horario_trabalho']['regime_recomendado']}")
        print(f"Atenção: {res['analise_horario_trabalho']['pontos_atencao']}")
        print("\nPróximas ações recomendadas:")
        for passo in res['proximos_passos_recomendados']:
            print(f"  • {passo}")
        print("=======================================================\n")


def cmd_mine(args):
    profile = load_profile()
    print(f"[+] Iniciando mineração no modo: {args.modo.upper()}...")
    vagas = mine_all_opportunities(
        profile,
        modo=args.modo,
        min_schedule=args.min_schedule,
        min_stack=args.min_stack
    )

    VAGAS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(VAGAS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(vagas, f, ensure_ascii=False, indent=2)

    print(f"[OK] Total de vagas qualificadas encontradas: {len(vagas)}")
    print(f"[OK] Base persistida em: {VAGAS_DB_PATH}\n")

    top_vagas = vagas[:args.top]
    for i, v in enumerate(top_vagas, 1):
        sched = v['schedule_fit']
        print(f"#{i:02d} | [{v['origem']}] {v['titulo']}")
        print(f"     Empresa: {v['empresa']} | Local: {v['localizacao']}")
        print(f"     Score Composto: {v['score_composto']} pts | Horário: {sched['score_horario']}/100 ({sched['status']}) | Stack: {v['stack_score']}/100")
        print(f"     Link: {v['url']}")
        print(f"     Justificativa Horário: {sched['justificativa'][:120]}...\n")


def cmd_tailor(args):
    profile = load_profile()
    
    if not VAGAS_DB_PATH.exists():
        print(f"Base de vagas não encontrada. Execute 'mine' primeiro.", file=sys.stderr)
        return

    with open(VAGAS_DB_PATH, "r", encoding="utf-8") as f:
        vagas = json.load(f)

    vaga = None
    if args.id:
        vaga = next((v for v in vagas if v.get("id") == args.id), None)
    elif args.index is not None and 0 <= args.index < len(vagas):
        vaga = vagas[args.index]
    else:
        vaga = vagas[0] if vagas else None

    if not vaga:
        print("Vaga especificada não encontrada.", file=sys.stderr)
        return

    cv_res = calibrate_resume_for_job(profile, vaga)
    pitch_res = generate_cover_pitch(profile, vaga)

    print("\n=======================================================")
    print(f"  PACOTE DE CANDIDATURA GERADO: {cv_res['vaga_alvo']}")
    print("=======================================================\n")
    print("--- CURRÍCULO CUSTOMIZADO (MARKDOWN) ---\n")
    print(cv_res['curriculo_markdown'])
    print("\n-------------------------------------------------------")
    print("--- COLD PITCH EM INGLÊS ---\n")
    print(pitch_res['pitch_ingles'])
    print("\n-------------------------------------------------------")
    print("--- COLD PITCH EM PORTUGUÊS ---\n")
    print(pitch_res['pitch_portugues'])
    print("=======================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Career Copilot — Agente de Carreira e Vagas Assíncronas")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # Comando: profile
    p_profile = subparsers.add_parser("profile", help="Analisa o perfil e a viabilidade da rotina desejada")
    p_profile.add_argument("--json", action="store_true", help="Saída estrita em JSON")

    # Comando: mine
    p_mine = subparsers.add_parser("mine", help="Minera vagas qualificadas em tempo real")
    p_mine.add_argument("--modo", choices=["todos", "internacional", "nacional"], default="todos")
    p_mine.add_argument("--min-schedule", type=int, default=50, help="Score mínimo de horário/rotina")
    p_mine.add_argument("--min-stack", type=int, default=25, help="Score mínimo de stack técnica")
    p_mine.add_argument("--top", type=int, default=10, help="Quantidade a exibir")

    # Comando: tailor
    p_tailor = subparsers.add_parser("tailor", help="Gera currículo e mensagem de pitch para uma vaga")
    p_tailor.add_argument("--id", type=str, help="ID da vaga na base")
    p_tailor.add_argument("--index", type=int, help="Índice da vaga (ex: 0 para a primeira)")

    args = parser.parse_args()

    if args.command == "profile":
        cmd_profile(args)
    elif args.command == "mine":
        cmd_mine(args)
    elif args.command == "tailor":
        cmd_tailor(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
