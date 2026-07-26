"""AutoRE RHF prompt templates (open-domain variant)."""

from __future__ import annotations


def relation_prompt(passage: str) -> str:
    return (
        "Given a passage:\n"
        f"{passage}\n\n"
        "List any underlying relations between entities mentioned in the passage.\n"
        "Output one relation phrase per line. If none, output: no relation"
    )


def head_prompt(relation: str, passage: str) -> str:
    return (
        f"Given a relation: {relation}\n"
        f"And a passage:\n{passage}\n\n"
        "List entities that can be identified as suitable subjects (heads) for the relation.\n"
        "Output one entity per line. If none, output: no entity"
    )


def facts_prompt(relation: str, subject: str, passage: str) -> str:
    return (
        f"Given relation: {relation}\n"
        f"Subject: {subject}\n"
        f"Passage:\n{passage}\n\n"
        "List all triple facts as [subject, relation, object] one per line.\n"
        "If none, output: no fact"
    )
