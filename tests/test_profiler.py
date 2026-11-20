from src.profiler import analyze_career_profile, detect_job_gaps


def test_career_profiler():
    profile = {
        "candidato": {"nome": "Dev Teste", "titulo_principal": "Python Engineer", "localizacao": "SP"},
        "preferencias_carreira": {"senioridade_alvo": ["Mid-Level"], "cargos_alvo": ["Backend Developer"]},
        "horario_trabalho_desejado": {
            "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
            "carga_semanal_horas": 20,
            "permite_reunioes_horario_comercial": False
        },
        "competencias": {
            "principais": ["Python", "FastAPI", "SQL", "Docker"],
            "secundarias": ["Git"],
            "idiomas": {"ingles": "Técnico / Intermediário-Avançado"}
        },
        "historico_profissional": [
            {"cargo": "Desenvolvedor Júnior", "empresa": "Tech A", "atividades": ["Python", "Testes"]}
        ]
    }

    res = analyze_career_profile(profile)
    assert res["candidato"]["nome"] == "Dev Teste"
    assert res["analise_horario_trabalho"]["status"] == "ALTA"
    assert res["diagnostico_carreira"]["readiness_internacional_score"] >= 70
