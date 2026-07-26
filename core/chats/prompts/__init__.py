"""Chat orchestration prompts."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPTS_DIR = Path(__file__).resolve().parent
_ENV = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(enabled_extensions=()),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt(template_name: str, **context: object) -> str:
    return _ENV.get_template(template_name).render(**context)
