"""Configurações globais, logging seguro para stdio e persistência atômica."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from .models import CandidateProfile

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIGS_DIR = BASE_DIR / "configs"
DATA_DIR = BASE_DIR / "data"

PERFIL_PATH = CONFIGS_DIR / "perfil.json"
PERFIL_TEMPLATE_PATH = CONFIGS_DIR / "perfil_template.json"
VAGAS_DB_PATH = DATA_DIR / "vagas_mineradas.json"
ATS_BOARDS_PATH = CONFIGS_DIR / "ats_boards.json"
HTTP_CACHE_DIR = DATA_DIR / "http_cache"
RESUMES_OUTPUT_DIR = DATA_DIR / "curriculos_gerados"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
APPLICATIONS_LOG_PATH = DATA_DIR / "candidaturas_log.json"

USER_AGENT = (
    "CareerCopilot/2.0 (+https://github.com/VictorRubinec/career-copilot; "
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36)"
)


def get_data_dir() -> Path:
    """Retorna o diretório de dados, respeitando CAREER_COPILOT_DATA_DIR."""
    override = os.environ.get("CAREER_COPILOT_DATA_DIR")
    return Path(override) if override else DATA_DIR


def get_vagas_db_path() -> Path:
    """Retorna o caminho da base de vagas mineradas."""
    return get_data_dir() / "vagas_mineradas.json"


def get_cache_dir() -> Path:
    """Retorna o diretório de cache HTTP, respeitando CAREER_COPILOT_CACHE_DIR."""
    override = os.environ.get("CAREER_COPILOT_CACHE_DIR")
    return Path(override) if override else get_data_dir() / "http_cache"


def get_resumes_output_dir() -> Path:
    """Retorna o diretório de saída para currículos compilados em PDF/HTML."""
    return get_data_dir() / "curriculos_gerados"


def get_browser_profile_dir() -> Path:
    """Retorna o diretório persistente de perfil do navegador (pré-autenticado)."""
    override = os.environ.get("CAREER_COPILOT_BROWSER_PROFILE_DIR")
    return Path(override) if override else get_data_dir() / "browser_profile"


def get_applications_log_path() -> Path:
    """Retorna o caminho do registro local de candidaturas assistidas (idempotência)."""
    return get_data_dir() / "candidaturas_log.json"


def get_profile_path() -> Path:
    """Retorna o caminho do perfil ativo ou template, respeitando variável de ambiente."""
    override = os.environ.get("CAREER_COPILOT_PROFILE_PATH")
    if override:
        return Path(override)
    return PERFIL_PATH if PERFIL_PATH.exists() else PERFIL_TEMPLATE_PATH


def get_ats_boards_path() -> Path:
    """Retorna o caminho da configuração de boards ATS públicos."""
    override = os.environ.get("CAREER_COPILOT_ATS_BOARDS_PATH")
    return Path(override) if override else ATS_BOARDS_PATH


def get_logger(name: str) -> logging.Logger:
    """Retorna logger padronizado direcionado estritamente para stderr."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    level_name = os.environ.get("CAREER_COPILOT_LOG_LEVEL", "WARNING").upper()
    logger.setLevel(getattr(logging, level_name, logging.WARNING))
    logger.propagate = False
    return logger


def _atomic_write_via_temp(
    path: Path,
    mode: str,
    writer_fn: Callable[[Any], None],
    encoding: str | None = None,
) -> None:
    """Grava arquivo de forma atômica via arquivo temporário irmão + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        kwargs: dict[str, Any] = {
            "mode": mode,
            "dir": path.parent,
            "prefix": f".{path.stem}_",
            "suffix": ".tmp",
            "delete": False,
        }
        if encoding is not None:
            kwargs["encoding"] = encoding
        with tempfile.NamedTemporaryFile(**kwargs) as tmp_file:
            tmp_path = Path(tmp_file.name)
            writer_fn(tmp_file)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    """Grava JSON de forma atômica via arquivo temporário + os.replace."""
    _atomic_write_via_temp(
        path,
        mode="w",
        encoding="utf-8",
        writer_fn=lambda f: json.dump(data, f, ensure_ascii=False, indent=2),
    )


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Grava bytes binários (ex.: PDF) de forma atômica via arquivo temporário + os.replace."""
    _atomic_write_via_temp(
        path,
        mode="wb",
        writer_fn=lambda f: f.write(payload),
    )


def load_profile_model(path: Path | None = None) -> CandidateProfile:
    """Carrega e valida o perfil do candidato como modelo Pydantic v2."""
    target_path = path if path is not None else get_profile_path()
    if not target_path.exists():
        raise FileNotFoundError(f"Arquivo de perfil não encontrado em {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return CandidateProfile.model_validate(raw)


def load_profile(path: Path | None = None) -> dict[str, Any]:
    """Carrega o perfil ativo do usuário validado como dicionário compatível."""
    return load_profile_model(path).model_dump()


def save_profile(
    data: dict[str, Any] | CandidateProfile,
    path: Path | None = None,
) -> None:
    """Valida e salva dados no arquivo de perfil ativo de forma atômica."""
    profile = (
        data if isinstance(data, CandidateProfile) else CandidateProfile.model_validate(data)
    )
    if path is not None:
        target = path
    else:
        override = os.environ.get("CAREER_COPILOT_PROFILE_PATH")
        target = Path(override) if override else PERFIL_PATH
    atomic_write_json(target, profile.model_dump())


def load_ats_boards(path: Path | None = None) -> dict[str, list[str]]:
    """Carrega os slugs de empresas por provedor ATS a partir de configs/ats_boards.json."""
    target = path if path is not None else get_ats_boards_path()
    default_boards: dict[str, list[str]] = {
        "greenhouse": [],
        "ashby": [],
        "lever": [],
    }
    if not target.exists():
        return default_boards

    with open(target, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return default_boards

    result: dict[str, list[str]] = {}
    for key in ("greenhouse", "ashby", "lever"):
        items = raw.get(key, [])
        if isinstance(items, list):
            result[key] = [str(item).strip() for item in items if str(item).strip()]
        else:
            result[key] = []
    return result
