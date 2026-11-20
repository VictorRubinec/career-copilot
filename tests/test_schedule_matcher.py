from src.evaluators.schedule_matcher import evaluate_schedule_fit


def test_schedule_fit_async_job():
    schedule = {
        "tipo_rotina": "Segundo Trabalho Noturno",
        "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
        "turnos_aceitos": ["noturno", "flexivel_assincrono"],
        "permite_reunioes_horario_comercial": False,
    }

    job_text = (
        "We are an async-first company with flexible hours and no core hours. "
        "Work whenever you want as a contractor."
    )
    res = evaluate_schedule_fit(job_text, "Worldwide", "Contract", schedule)

    assert res["status"] == "COMPATIVEL"
    assert res["classificacao_exibicao"] == "[COMPATÍVEL]"
    assert res["score_horario"] >= 75
    assert len(res["sinais_positivos"]) >= 3
    assert len(res["red_flags"]) == 0


def test_schedule_fit_strict_hours():
    schedule = {
        "tipo_rotina": "Segundo Trabalho Noturno",
        "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
        "turnos_aceitos": ["noturno"],
        "permite_reunioes_horario_comercial": False,
    }

    job_text = "Mandatory 9-5 core hours required. Daily standup at 10am is strictly enforced."
    res = evaluate_schedule_fit(job_text, "US", "Full-time", schedule)

    assert res["status"] == "INCOMPATIVEL"
    assert res["classificacao_exibicao"] == "[INCOMPATÍVEL]"
    assert res["score_horario"] < 50
    assert len(res["red_flags"]) >= 1


def test_neuroscale_regression_inperson_relocate_blocked():
    schedule = {
        "tipo_rotina": "Segundo Trabalho / Turno Noturno",
        "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
        "permite_reunioes_horario_comercial": False,
    }
    job_text = (
        "Build asynchronous processing systems for B2B and B2C SaaS experiences. "
        "Ability and willingness to relocate to Northern VA/DC. "
        "Flexibility: Flexible hours, in-person."
    )
    res = evaluate_schedule_fit(job_text, "USA", "Full-Time", schedule)

    assert res["status"] == "INCOMPATIVEL"
    assert res["score_horario"] <= 10
    assert any("in-person" in f or "relocation" in f for f in res["red_flags"])
    assert "b2b contract" not in res["sinais_positivos"]
    assert "asynchronous work/culture" not in res["sinais_positivos"]


def test_parental_leave_return_part_time_and_remote_or_hybrid_not_penalized():
    schedule = {"permite_reunioes_horario_comercial": False}
    job_text = (
        "Remote-first role in Brazil. We offer hybrid and remote options. "
        "Parents may return part-time while they get settled."
    )
    res = evaluate_schedule_fit(job_text, "Brazil", "Full-Time", schedule)

    assert "part-time" not in res["sinais_positivos"]
    assert "híbrido/hybrid" not in res["red_flags"]


def test_permite_reunioes_comercial_changes_penalty():
    job_text = "Remote contractor position with daily standup at 10am BRT."

    strict = evaluate_schedule_fit(
        job_text,
        "Worldwide",
        "Contract",
        {"permite_reunioes_horario_comercial": False},
    )
    tolerant = evaluate_schedule_fit(
        job_text,
        "Worldwide",
        "Contract",
        {"permite_reunioes_horario_comercial": True},
    )

    assert strict["status"] == "INCOMPATIVEL"
    assert strict["score_horario"] <= 45
    assert tolerant["score_horario"] > strict["score_horario"]
    assert tolerant["status"] == "PARCIALMENTE_COMPATIVEL"
    assert tolerant["classificacao_exibicao"] == "[PARCIALMENTE COMPATÍVEL]"


def test_fixed_timezone_and_camera_monitoring_veto():
    job_text = "EST business hours required. Cameras always on and time tracker required."
    res = evaluate_schedule_fit(
        job_text,
        "Americas",
        "Contract",
        {"permite_reunioes_horario_comercial": False},
    )
    assert res["status"] == "INCOMPATIVEL"
    assert res["score_horario"] <= 20
    assert len(res["red_flags"]) >= 2
