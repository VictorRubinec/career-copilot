import json
import logging
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import (
    atomic_write_json,
    get_logger,
    load_ats_boards,
    load_profile,
    load_profile_model,
    save_profile,
)
from src.models import CandidateProfile, EducationEntry, ScheduleFitResult


def test_candidate_profile_validation_and_education_coercion():
    profile = CandidateProfile.model_validate(
        {
            "candidato": {"nome": "Ana Dev"},
            "formacao_e_certificacoes": [
                "Engenharia de Software",
                {"titulo": "AWS Certified Developer", "detalhe": "Associate"},
            ],
        }
    )
    assert profile.candidato.nome == "Ana Dev"
    assert profile.horario_trabalho_desejado.carga_semanal_horas == 20
    assert isinstance(profile.formacao_e_certificacoes[0], EducationEntry)
    assert profile.formacao_e_certificacoes[0].titulo == "Engenharia de Software"
    assert profile.formacao_e_certificacoes[1].detalhe == "Associate"


def test_schedule_fit_result_bounds():
    with pytest.raises(ValidationError):
        ScheduleFitResult(
            score_horario=120,
            status="COMPATIVEL",
            classificacao_exibicao="[COMPATÍVEL]",
            justificativa="Inválido",
        )


def test_profile_save_load_and_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_profile_path = tmp_path / "custom_perfil.json"
    monkeypatch.setenv("CAREER_COPILOT_PROFILE_PATH", str(custom_profile_path))

    payload = {
        "candidato": {
            "nome": "Carlos Remoto",
            "titulo_principal": "Backend Python",
            "localizacao": "Curitiba, PR",
            "contato": {"email": "carlos@example.com"},
        },
        "competencias": {"principais": ["Python", "FastAPI"]},
    }
    save_profile(payload)
    assert custom_profile_path.exists()

    loaded_dict = load_profile()
    loaded_model = load_profile_model()
    assert loaded_dict["candidato"]["nome"] == "Carlos Remoto"
    assert loaded_model.competencias.principais == ["Python", "FastAPI"]


def test_atomic_write_json_leaves_no_temp_files(tmp_path: Path):
    target = tmp_path / "nested" / "dados.json"
    atomic_write_json(target, {"ok": True, "itens": [1, 2]})
    atomic_write_json(target, {"ok": True, "itens": [1, 2, 3]})

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True, "itens": [1, 2, 3]}
    leftovers = [p for p in target.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_load_ats_boards_missing_and_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("CAREER_COPILOT_ATS_BOARDS_PATH", str(missing))
    assert load_ats_boards() == {"greenhouse": [], "ashby": [], "lever": []}

    present = tmp_path / "ats_boards.json"
    present.write_text(
        json.dumps({"greenhouse": ["gitlab"], "ashby": ["posthog"], "lever": ["toptal"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAREER_COPILOT_ATS_BOARDS_PATH", str(present))
    assert load_ats_boards() == {
        "greenhouse": ["gitlab"],
        "ashby": ["posthog"],
        "lever": ["toptal"],
    }


def test_logger_writes_only_to_stderr():
    logger = get_logger("tests.stderr_check")
    assert logger.propagate is False
    assert len(logger.handlers) == 1
    handler = logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
