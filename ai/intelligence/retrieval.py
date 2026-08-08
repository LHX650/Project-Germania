"""Question classification and dynamic vehicle mention matching."""

from __future__ import annotations

from ai.intelligence.models import QuestionIntent


def classify_question(question: str) -> QuestionIntent:
    """Classify a question without hard-coding any vehicle identity."""

    text = _normalize(question)
    if any(token in text for token in ("daily brief", "market brief", "overview")):
        return "daily_brief"
    if any(token in text for token in ("explain alert", "why triggered", "alert")):
        return "alert_explanation"
    if any(token in text for token in ("compare", "versus", " vs ", "difference")):
        return "vehicle_comparison"
    if any(
        token in text
        for token in ("highest opportunity", "best opportunity", "opportunities")
    ):
        return "highest_opportunity"
    if any(
        token in text for token in ("main risks", "market risk", "risk in", "risks in")
    ):
        return "market_risk"
    if any(
        token in text
        for token in ("under pressure", "price pressure", "inventory pressure")
    ):
        return "vehicle_pressure"
    return "general"


def mentioned_vehicle_keys(
    question: str,
    vehicle_keys: tuple[str, ...],
) -> tuple[str, ...]:
    """Return dynamically mentioned report vehicles in question order."""

    normalized_question = _normalize(question)
    matches: list[tuple[int, str]] = []
    for key in vehicle_keys:
        normalized_key = _normalize(key)
        position = normalized_question.find(normalized_key)
        if position >= 0:
            matches.append((position, key))
            continue
        parts = normalized_key.split()
        model = " ".join(parts[1:])
        if model and len(model) >= 3:
            position = normalized_question.find(model)
            if position >= 0:
                matches.append((position, key))
    return tuple(key for _, key in sorted(matches))


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())
