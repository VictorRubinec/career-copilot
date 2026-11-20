import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIGS_DIR = BASE_DIR / "configs"
DATA_DIR = BASE_DIR / "data"

PERFIL_PATH = CONFIGS_DIR / "perfil.json"
PERFIL_TEMPLATE_PATH = CONFIGS_DIR / "perfil_template.json"
VAGAS_DB_PATH = DATA_DIR / "vagas_mineradas.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def load_profile():
    """Carrega o perfil ativo do usuário ou o template de exemplo."""
    target_path = PERFIL_PATH if PERFIL_PATH.exists() else PERFIL_TEMPLATE_PATH
    if not target_path.exists():
        raise FileNotFoundError(f"Arquivo de perfil não encontrado em {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(data):
    """Salva dados no arquivo de perfil ativo."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PERFIL_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
