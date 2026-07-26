"""Prompt rendering for retrieval query refinement."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROMPTS_DIR = Path(__file__).resolve().parent
_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    autoescape=select_autoescape(default=False),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt(template_name: str, **context: object) -> str:
    template = _env.get_template(template_name)
    return template.render(**context)
