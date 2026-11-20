"""Módulo Copiloto Human-in-the-Loop para candidaturas assistidas via Playwright."""

from .assistant import HumanInTheLoopCopilot, prepare_assisted_application
from .form_mapper import (
    build_application_payload,
    detect_external_gate,
    has_prior_application_for_url,
    normalize_application_url,
    record_application_draft,
)

__all__ = [
    "HumanInTheLoopCopilot",
    "build_application_payload",
    "detect_external_gate",
    "has_prior_application_for_url",
    "normalize_application_url",
    "prepare_assisted_application",
    "record_application_draft",
]
