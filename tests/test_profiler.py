from src.profiler import analyze_career_profile, detect_job_gaps


def test_career_profiler():
    profile = {
        "candidato": {"nome": "Dev Teste", "titulo_principal": "Python Engineer", "localizacao": "SP"},
        "preferencias_carreira": {"senioridade_alvo": ["Mid-Level"], "cargos_alvo": ["Backend Developer"]},
        "horario_trabalho_desejado": {
            "janela_disponivel": {"segunda_a_sexta": "19:00 - 00:00"},
            "carga_semanal_horas": 20,
            "permite_reunioes_horario_comercial": False,
        },
        "competencias": {
            "principais": ["Python", "FastAPI", "SQL", "Docker"],
            "secundarias": ["Git"],
            "idiomas": {"ingles": "Técnico / Intermediário-Avançado"},
        },
        "historico_profissional": [
            {"cargo": "Desenvolvedor Júnior", "empresa": "Tech A", "atividades": ["Python", "Testes"]}
        ],
    }

    res = analyze_career_profile(profile)
    assert res["candidato"]["nome"] == "Dev Teste"
    assert res["analise_horario_trabalho"]["status"] == "ALTA"
    assert res["diagnostico_carreira"]["readiness_internacional_score"] >= 70
    assert res["diagnostico_carreira"]["senioridade_estimada"] == "Júnior / Entry-Level"


def test_profiler_seniority_pleno_and_senior():
    pleno_profile = {
        "candidato": {"nome": "Pleno"},
        "horario_trabalho_desejado": {"carga_semanal_horas": 30, "permite_reunioes_horario_comercial": True},
        "historico_profissional": [
            {"cargo": "Backend Developer", "empresa": "A", "atividades": ["APIs"]},
            {"cargo": "Python Developer", "empresa": "B", "atividades": ["ETL"]},
        ],
    }
    res_pleno = analyze_career_profile(pleno_profile)
    assert res_pleno["diagnostico_carreira"]["senioridade_estimada"] == "Pleno / Mid-Level"
    assert res_pleno["analise_horario_trabalho"]["status"] == "MODERADA"

    senior_profile = {
        "candidato": {"nome": "Senior"},
        "historico_profissional": [
            {"cargo": "Tech Lead", "empresa": "X", "atividades": ["Arquitetura"]}
        ],
    }
    res_senior = analyze_career_profile(senior_profile)
    assert res_senior["diagnostico_carreira"]["senioridade_estimada"] == "Senior / Specialist"


def test_detect_job_gaps_technical_and_fallback():
    profile = {
        "candidato": {"nome": "Dev"},
        "competencias": {
            "principais": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "secundarias": ["Git"],
        },
        "horario_trabalho_desejado": {"permite_reunioes_horario_comercial": False},
    }

    job_match = {
        "titulo": "Python Backend Contractor",
        "empresa": "AsyncCo",
        "origem": "Internacional",
        "localizacao": "Worldwide",
        "tipo_contrato": "Contractor",
        "descricao": "Async-first flexible hours role using Python, FastAPI, Docker and Kubernetes.",
    }
    report = detect_job_gaps(profile, job_match)
    assert report["aderencia_tecnica"]["match_pct"] == 75.0
    assert "kubernetes" in report["aderencia_tecnica"]["gaps_identificados"]
    assert "python" in report["aderencia_tecnica"]["skills_atendidas"]
    assert report["recomendacao_acao"].startswith("Aprovada")

    job_descriptive = {
        "titulo": "Automation Consultant",
        "empresa": "QuietCorp",
        "localizacao": "Anywhere",
        "tipo_contrato": "Freelance",
        "descricao": "Flexible schedule, async-first and self-directed consulting work.",
    }
    report_fallback = detect_job_gaps(profile, job_descriptive)
    assert report_fallback["aderencia_tecnica"]["match_pct"] == 75.0
    assert report_fallback["compatibilidade_horario"]["status"] == "COMPATIVEL"
