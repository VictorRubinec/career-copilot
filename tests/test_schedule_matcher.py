import pytest
from src.evaluators.schedule_matcher import evaluate_schedule_fit


def test_schedule_fit_async_job():
    schedule = {
        "tipo_rotina": "Segundo Trabalho Noturno",
        "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
        "turnos_aceitos": ["noturno", "flexivel_assincrono"],
        "permite_reunioes_horario_comercial": False
    }

    job_text = "We are an async-first company with flexible hours and no core hours. Work whenever you want as a contractor."
    res = evaluate_schedule_fit(job_text, "Worldwide", "Contract", schedule)

    assert res["status"] == "COMPATIVEL"
    assert res["score_horario"] >= 75
    assert len(res["sinais_positivos"]) >= 3
    assert len(res["red_flags"]) == 0


def test_schedule_fit_strict_hours():
    schedule = {
        "tipo_rotina": "Segundo Trabalho Noturno",
        "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
        "turnos_aceitos": ["noturno"],
        "permite_reunioes_horario_comercial": False
    }

    job_text = "Mandatory 9-5 core hours required. Daily standup at 10am is strictly enforced."
    res = evaluate_schedule_fit(job_text, "US", "Full-time", schedule)

    assert res["status"] == "INCOMPATIVEL"
    assert res["score_horario"] < 50
    assert len(res["red_flags"]) >= 1
