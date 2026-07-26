"""Prompt rendering for evaluate module."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROMPTS_DIR = Path(__file__).resolve().parent


def render_prompt(template_name: str, **context) -> str:
    env = Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
    )
    template = env.get_template(template_name)
    return template.render(**context)
