#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI Principal do Career Copilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .config import atomic_write_json, get_vagas_db_path, load_profile
from .copiloto import prepare_assisted_application
from .evaluators import evaluate_application_committee
from .miners import mine_all_opportunities
from .profiler import analyze_career_profile
from .tailor import (
    calibrate_resume_for_job,
    compile_resume_to_pdf,
    generate_cover_pitch,
)


def _load_job_from_db(job_id: str | None, index: int | None) -> dict[str, Any] | None:
    vagas_db = get_vagas_db_path()
    if not vagas_db.exists():
        print("Base de vagas não encontrada. Execute 'mine' primeiro.", file=sys.stderr)
        return None

    with open(vagas_db, "r", encoding="utf-8") as f:
        vagas = json.load(f)

    if not isinstance(vagas, list) or not vagas:
        print("Base de vagas vazia.", file=sys.stderr)
        return None

    if job_id:
        vaga = next((item for item in vagas if item.get("id") == job_id), None)
    elif index is not None and 0 <= index < len(vagas):
        vaga = vagas[index]
    else:
        vaga = vagas[0]

    if not vaga:
        print("Vaga especificada não encontrada.", file=sys.stderr)
        return None
    return vaga


def _read_resume_file(path_str: str | None) -> tuple[str | None, bool]:
    if not path_str:
        return None, True
    resume_path = Path(path_str)
    if not resume_path.exists():
        print(f"Arquivo de currículo não encontrado: {resume_path}", file=sys.stderr)
        return None, False
    return resume_path.read_text(encoding="utf-8"), True


def _print_pdf_report(pdf_res: dict[str, Any]) -> None:
    size_kb = round(pdf_res["tamanho_bytes"] / 1024.0, 1)
    meta = pdf_res["metadados"]
    print("\n=======================================================")
    print(f"  PDF A4 CORPORATIVO COMPILADO: {pdf_res['vaga_alvo']}")
    print("=======================================================")
    print(f"Arquivo PDF: {pdf_res['pdf_path']}")
    if pdf_res.get("html_path"):
        print(f"HTML Auxiliar: {pdf_res['html_path']}")
    print(
        f"Páginas: {pdf_res['paginas']} | Tamanho: {size_kb} KB | "
        f"ATS Legível: {'SIM' if pdf_res['ats_legivel'] else 'NÃO'}"
    )
    print(f"Título/Autor: {meta['title']} ({meta['author']})")
    print(f"SHA-256: {pdf_res['sha256']}")
    print("=======================================================\n")


def _print_copilot_report(session: dict[str, Any]) -> None:
    sched = session["compatibilidade_horario"]
    print("\n=======================================================")
    print(f"  COPILOTO HUMAN-IN-THE-LOOP: {session['vaga_alvo']}")
    print("=======================================================")
    print(
        f"Status: {session['status']} | "
        f"Submetido Automaticamente: {session['submetido_automaticamente']} | "
        f"Duplicata Prévia: {session['duplicata_detectada']}"
    )
    print(
        f"Rotina: {sched['classificacao_exibicao']} ({sched['score_horario']}/100) | "
        f"URL: {session['url_destino']}"
    )
    if session.get("curriculo_pdf_path"):
        print(f"Currículo PDF A4: {session['curriculo_pdf_path']}")
    print(f"Perfil Persistente: {session['perfil_navegador']}")
    if session.get("bloqueio_externo_detectado"):
        print(f"Gate Externo: {session['bloqueio_externo_detectado']}")

    filled = [c for c in session.get("campos_preenchidos", []) if c.get("preenchido")]
    if filled:
        print(f"\n--- Campos Preenchidos ({len(filled)}) ---")
        for item in filled:
            print(f"  • {item['campo_logico']}: {item['valor_preview']}")

    if session.get("campos_pendentes_humano"):
        print("\n--- Campos Obrigatórios Pendentes (Decisão Humana) ---")
        for pending in session["campos_pendentes_humano"]:
            print(f"  [!] {pending}")

    print(f"\nAviso: {session['aviso_seguranca']}")
    if session.get("proximos_passos_humano"):
        print("Próximos passos:")
        for step in session["proximos_passos_humano"]:
            print(f"  -> {step}")
    print("=======================================================\n")


def _print_committee_report(review: dict[str, Any]) -> None:
    sched = review["compatibilidade_horario"]
    veto = review["veto"]
    print("\n=======================================================")
    print(f"  BANCA EXAMINADORA (7 PERSONAS): {review['vaga_alvo']}")
    print("=======================================================")
    print(
        f"Veredito: {review['veredito']} | Média Geral: {review['media_geral']:.2f}/10 "
        f"(Corte: {review['limiar_aprovacao']:.1f})"
    )
    print(
        f"Rotina: {sched['classificacao_exibicao']} ({sched['score_horario']}/100) | "
        f"Modo: {review['modo_avaliacao']}"
    )
    if veto["ativo"]:
        print(f"VETO AUTOMÁTICO ({', '.join(veto['personas_vetadoras'])}):")
        for motivo in veto["motivos"]:
            print(f"  [!] {motivo}")

    print("\n--- Notas Individuais ---")
    for item in review["avaliacoes"]:
        print(f"  • {item['persona_nome']:<22} {item['nota']:>4.1f}/10 — {item['justificativa']}")

    if review["plano_acao_prioritario"]:
        print("\n--- Plano de Ação Prioritário ---")
        for acao in review["plano_acao_prioritario"]:
            print(f"  -> {acao}")

    print(f"\nResumo: {review['resumo_executivo']}")
    print("=======================================================\n")


def cmd_profile(args: argparse.Namespace) -> None:
    profile = load_profile()
    res = analyze_career_profile(profile)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    print("\n=======================================================")
    print("         DIAGNÓSTICO DE CARREIRA E PERFIL")
    print("=======================================================")
    print(f"Candidato: {res['candidato']['nome']} ({res['candidato']['titulo']})")
    print(f"Localização: {res['candidato']['localizacao']}")
    print(f"Senioridade Estimada: {res['diagnostico_carreira']['senioridade_estimada']}")
    print(f"Nível de Autonomia: {res['diagnostico_carreira']['nivel_autonomia']}")
    print(
        f"Índice de Prontidão Internacional: "
        f"{res['diagnostico_carreira']['readiness_internacional_score']}/100"
    )
    print("\n--- Análise de Horário e Rotina Desejada ---")
    print(f"Status de Viabilidade: {res['analise_horario_trabalho']['status']}")
    print(f"Janela Declarada: {res['analise_horario_trabalho']['janela_declarada']}")
    print(f"Carga Alvo: {res['analise_horario_trabalho']['carga_alvo']}")
    print(f"Regime Recomendado: {res['analise_horario_trabalho']['regime_recomendado']}")
    print(f"Atenção: {res['analise_horario_trabalho']['pontos_atencao']}")
    print("\nPróximas ações recomendadas:")
    for passo in res["proximos_passos_recomendados"]:
        print(f"  • {passo}")
    print("=======================================================\n")


def cmd_mine(args: argparse.Namespace) -> None:
    profile = load_profile()
    fontes = (
        [item.strip() for item in args.fontes.split(",") if item.strip()]
        if args.fontes
        else None
    )
    print(f"[+] Iniciando mineração no modo: {args.modo.upper()}...")
    vagas = mine_all_opportunities(
        profile,
        modo=args.modo,
        min_schedule=args.min_schedule,
        min_stack=args.min_stack,
        fontes=fontes,
        use_cache=not args.no_cache,
    )

    vagas_db = get_vagas_db_path()
    atomic_write_json(vagas_db, vagas)

    print(f"[OK] Total de vagas qualificadas encontradas: {len(vagas)}")
    print(f"[OK] Base persistida em: {vagas_db}\n")

    top_vagas = vagas[: args.top]
    for i, vaga in enumerate(top_vagas, 1):
        sched = vaga["schedule_fit"]
        classificacao = sched.get("classificacao_exibicao", f"[{sched['status']}]")
        print(f"#{i:02d} | [{vaga['origem']}] ({vaga['fonte']}) {vaga['titulo']}")
        print(f"     Empresa: {vaga['empresa']} | Local: {vaga['localizacao']}")
        print(
            f"     Score Composto: {vaga['score_composto']} pts | "
            f"Horário: {sched['score_horario']}/100 {classificacao} | "
            f"Stack: {vaga['stack_score']}/100"
        )
        print(f"     Link: {vaga['url']}")
        print(f"     Justificativa Horário: {sched['justificativa'][:120]}...\n")


def cmd_tailor(args: argparse.Namespace) -> None:
    profile = load_profile()
    vaga = _load_job_from_db(args.id, args.index)
    if not vaga:
        return

    cv_res = calibrate_resume_for_job(profile, vaga)
    pitch_res = generate_cover_pitch(profile, vaga)

    print("\n=======================================================")
    print(f"  PACOTE DE CANDIDATURA GERADO: {cv_res['vaga_alvo']}")
    print("=======================================================\n")
    print("--- CURRÍCULO CUSTOMIZADO (MARKDOWN) ---\n")
    print(cv_res["curriculo_markdown"])
    print("\n-------------------------------------------------------")
    print("--- COLD PITCH EM INGLÊS ---\n")
    print(pitch_res["pitch_ingles"])
    print("\n-------------------------------------------------------")
    print("--- COLD PITCH EM PORTUGUÊS ---\n")
    print(pitch_res["pitch_portugues"])
    print("=======================================================\n")

    if getattr(args, "with_review", False):
        review = evaluate_application_committee(
            profile,
            vaga,
            resume_markdown=cv_res["curriculo_markdown"],
        )
        _print_committee_report(review)

    if getattr(args, "pdf", False):
        pdf_res = compile_resume_to_pdf(
            profile,
            vaga,
            resume_markdown=cv_res["curriculo_markdown"],
            output_path=getattr(args, "output", None),
            load_web_fonts=not getattr(args, "offline_fonts", False),
        )
        _print_pdf_report(pdf_res)


def cmd_review(args: argparse.Namespace) -> None:
    profile = load_profile()
    vaga = _load_job_from_db(args.id, args.index)
    if not vaga:
        return

    resume_md, ok = _read_resume_file(args.resume)
    if not ok:
        return

    review = evaluate_application_committee(profile, vaga, resume_markdown=resume_md)
    if args.json:
        print(json.dumps(review, ensure_ascii=False, indent=2))
    else:
        _print_committee_report(review)


def cmd_pdf(args: argparse.Namespace) -> None:
    profile = load_profile()
    if args.id or get_vagas_db_path().exists():
        vaga = _load_job_from_db(args.id, args.index)
        if not vaga:
            return
    else:
        vaga = {}

    resume_md, ok = _read_resume_file(args.resume)
    if not ok:
        return

    pdf_res = compile_resume_to_pdf(
        profile,
        vaga,
        resume_markdown=resume_md,
        output_path=args.output,
        save_html=args.save_html,
        load_web_fonts=not args.offline_fonts,
    )
    if args.json:
        print(json.dumps(pdf_res, ensure_ascii=False, indent=2))
    else:
        _print_pdf_report(pdf_res)


def cmd_apply(args: argparse.Namespace) -> None:
    profile = load_profile()
    if args.url and not args.id:
        vaga: dict[str, Any] = {
            "titulo": "Vaga Externa",
            "empresa": "Empresa Alvo",
            "url": args.url,
            "localizacao": "Worldwide",
            "tipo_contrato": "Remote",
            "descricao": "",
        }
    else:
        loaded = _load_job_from_db(args.id, args.index)
        if not loaded:
            return
        vaga = dict(loaded)
        if args.url:
            vaga["url"] = args.url

    session = prepare_assisted_application(
        profile,
        vaga,
        pdf_path=args.pdf_path,
        load_web_fonts=not args.offline_fonts,
        dry_run=args.dry_run,
        allow_schedule_conflict=args.allow_conflict,
        wait_for_human=not args.dry_run,
    )
    if args.json:
        print(json.dumps(session, ensure_ascii=False, indent=2))
    else:
        _print_copilot_report(session)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Career Copilot — Agente de Carreira e Vagas Assíncronas"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    p_profile = subparsers.add_parser(
        "profile", help="Analisa o perfil e a viabilidade da rotina desejada"
    )
    p_profile.add_argument("--json", action="store_true", help="Saída estrita em JSON")

    p_mine = subparsers.add_parser("mine", help="Minera vagas qualificadas em tempo real")
    p_mine.add_argument(
        "--modo", choices=["todos", "internacional", "nacional"], default="todos"
    )
    p_mine.add_argument(
        "--min-schedule", type=int, default=50, help="Score mínimo de horário/rotina"
    )
    p_mine.add_argument(
        "--min-stack", type=int, default=25, help="Score mínimo de stack técnica"
    )
    p_mine.add_argument(
        "--fontes",
        type=str,
        default=None,
        help="Fontes separadas por vírgula (ex: greenhouse,ashby,lever,hackernews)",
    )
    p_mine.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignora o cache HTTP local e força coleta em tempo real",
    )
    p_mine.add_argument("--top", type=int, default=10, help="Quantidade a exibir")

    p_tailor = subparsers.add_parser(
        "tailor", help="Gera currículo e mensagem de pitch para uma vaga"
    )
    p_tailor.add_argument("--id", type=str, help="ID da vaga na base")
    p_tailor.add_argument(
        "--index", type=int, help="Índice da vaga (ex: 0 para a primeira)"
    )
    p_tailor.add_argument(
        "--with-review",
        action="store_true",
        help="Executa a Banca Examinadora (7 Personas) logo após calibrar o currículo",
    )
    p_tailor.add_argument(
        "--pdf",
        action="store_true",
        help="Compila também o currículo calibrado para PDF A4 corporativo",
    )
    p_tailor.add_argument(
        "--output",
        type=str,
        default=None,
        help="Caminho opcional do PDF de saída quando --pdf estiver ativo",
    )
    p_tailor.add_argument(
        "--offline-fonts",
        action="store_true",
        help="Não busca fontes Google Fonts externas ao gerar PDF",
    )

    p_review = subparsers.add_parser(
        "review",
        help="Avalia currículo e vaga com a Banca Examinadora das 7 Personas",
    )
    p_review.add_argument("--id", type=str, help="ID da vaga na base")
    p_review.add_argument(
        "--index", type=int, default=0, help="Índice da vaga (padrão: 0)"
    )
    p_review.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Caminho opcional para currículo customizado em Markdown",
    )
    p_review.add_argument("--json", action="store_true", help="Saída estrita em JSON")

    p_pdf = subparsers.add_parser(
        "pdf",
        help="Compila currículo para PDF A4 corporativo via Playwright Chromium headless",
    )
    p_pdf.add_argument("--id", type=str, help="ID da vaga na base")
    p_pdf.add_argument(
        "--index", type=int, default=0, help="Índice da vaga (padrão: 0)"
    )
    p_pdf.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Caminho opcional para currículo customizado em Markdown",
    )
    p_pdf.add_argument(
        "--output",
        type=str,
        default=None,
        help="Caminho de destino para o arquivo PDF gerado",
    )
    p_pdf.add_argument(
        "--save-html",
        action="store_true",
        help="Salva também o HTML corporativo intermediário ao lado do PDF",
    )
    p_pdf.add_argument(
        "--offline-fonts",
        action="store_true",
        help="Usa apenas fontes do sistema sem carregar Google Fonts",
    )
    p_pdf.add_argument("--json", action="store_true", help="Saída estrita em JSON")

    p_apply = subparsers.add_parser(
        "apply",
        help="Copiloto Human-in-the-Loop: preenche candidatura via Playwright e pausa antes de submeter",
    )
    p_apply.add_argument("--id", type=str, help="ID da vaga na base")
    p_apply.add_argument(
        "--index", type=int, default=0, help="Índice da vaga (padrão: 0)"
    )
    p_apply.add_argument(
        "--url",
        type=str,
        default=None,
        help="URL direta da vaga (opcional, substitui ou dispensa base de vagas)",
    )
    p_apply.add_argument(
        "--pdf-path",
        type=str,
        default=None,
        help="Caminho de PDF A4 já compilado (se omitido, compila automaticamente)",
    )
    p_apply.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepara payload e PDF sem abrir janela do navegador",
    )
    p_apply.add_argument(
        "--allow-conflict",
        action="store_true",
        help="Permite abrir mesmo quando houver alerta de conflito de horário",
    )
    p_apply.add_argument(
        "--offline-fonts",
        action="store_true",
        help="Não busca fontes Google Fonts externas caso compile o PDF",
    )
    p_apply.add_argument("--json", action="store_true", help="Saída estrita em JSON")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "profile":
        cmd_profile(args)
    elif args.command == "mine":
        cmd_mine(args)
    elif args.command == "tailor":
        cmd_tailor(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "pdf":
        cmd_pdf(args)
    elif args.command == "apply":
        cmd_apply(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
