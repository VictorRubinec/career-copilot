from src.tailor import calibrate_resume_for_job, generate_cover_pitch


def test_tailor_uses_dynamic_profile_with_zero_hardcodes():
    generic_profile = {
        "candidato": {
            "nome": "Maria Oliveira",
            "titulo_principal": "Engenheira de Dados & Automação",
            "localizacao": "Belo Horizonte, MG",
            "contato": {
                "email": "maria@exemplo.com",
                "telefone": "+55 31 99999-0000",
                "linkedin": "https://linkedin.com/in/maria",
                "github": "",
                "portfolio": "",
            },
        },
        "preferencias_carreira": {
            "regimes_contratuais": ["Contractor B2B"],
        },
        "horario_trabalho_desejado": {
            "janela_disponivel": {"segunda_a_sexta": "19:30 - 23:30 BRT"},
        },
        "competencias": {
            "principais": ["Java", "Python", "Airflow", "Docker"],
            "secundarias": ["AWS"],
            "idiomas": {"portugues": "Nativo", "ingles": "C1 Avançado"},
        },
        "historico_profissional": [
            {
                "empresa": "Acme FinTech",
                "cargo": "Data Engineer",
                "periodo": "2024 - 2026",
                "atividades": ["Construiu pipelines em Airflow e Python."],
            }
        ],
    }
    job = {
        "titulo": "Python Automation Engineer",
        "empresa": "RemoteLabs",
        "matches_stack": ["docker", "python"],
    }

    cv = calibrate_resume_for_job(generic_profile, job)
    md = cv["curriculo_markdown"]
    assert "Maria Oliveira" in md
    assert "Acme FinTech" in md
    assert "C1 Avançado" in md
    assert "TIVIT" not in md
    assert "Ciência da Computação" not in md
    assert "Six Sigma" not in md
    assert "Formação Acadêmica & Certificações" not in md
    assert "[GitHub]" not in md

    # Matched skills ('Python', 'Docker') must precede unmatched ('Java', 'Airflow')
    skills_line = next(line for line in md.splitlines() if "Linguagens & Frameworks Principais" in line)
    assert skills_line.index("Python") < skills_line.index("Java")
    assert skills_line.index("Docker") < skills_line.index("Airflow")

    pitches = generate_cover_pitch(generic_profile, job)
    assert "TIVIT" not in pitches["pitch_ingles"]
    assert "TIVIT" not in pitches["pitch_portugues"]
    assert "Acme FinTech" in pitches["pitch_ingles"]
    assert "Acme FinTech" in pitches["pitch_portugues"]
    assert "maria@exemplo.com" in pitches["pitch_ingles"]


def test_tailor_renders_education_and_handles_empty_history():
    minimal_profile = {
        "candidato": {
            "nome": "Lucas Entry",
            "contato": {"email": "lucas@exemplo.com"},
        },
        "competencias": {"principais": ["Python", "SQL"]},
        "formacao_e_certificacoes": [
            "Sistemas de Informação",
            {"titulo": "PCEP", "detalhe": "Python Institute"},
        ],
    }
    job = {"titulo": "Junior Python Dev", "empresa": "AsyncStartup"}

    cv = calibrate_resume_for_job(minimal_profile, job)
    md = cv["curriculo_markdown"]
    assert "Formação Acadêmica & Certificações" in md
    assert "**Sistemas de Informação**" in md
    assert "**PCEP** — Python Institute" in md
    assert "Experiência Profissional" not in md

    pitches = generate_cover_pitch(minimal_profile, job)
    assert "I bring practical experience designing reliable automation workflows" in pitches["pitch_ingles"]
    assert "None" not in pitches["pitch_ingles"]
    assert "None" not in pitches["pitch_portugues"]
