"""Validation and normalization shared by the API and agent graph."""

import unicodedata


def normalize_question(question: str) -> str:
    """Collapse whitespace and reject Unicode control characters except spacing."""
    if any(
        unicodedata.category(character) == "Cc" and character not in "\t\n\r"
        for character in question
    ):
        raise ValueError("La pregunta contiene caracteres de control no permitidos.")
    return " ".join(question.split())