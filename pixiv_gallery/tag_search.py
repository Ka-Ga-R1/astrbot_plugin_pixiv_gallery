"""Utilities for composing Japanese Pixiv discovery tags."""

from __future__ import annotations

import re

from .config import BOOKMARK_THRESHOLDS


def normalize_tag_terms(value: str) -> list[str]:
    """Read one or two Japanese Pixiv tag terms (LLM tool input is comma-separated)."""
    if not isinstance(value, str):
        return []
    terms = [term.strip() for term in re.split(r"[,，;；\r\n]+", value) if term.strip()]
    unique: list[str] = []
    for term in terms:
        if term not in unique:
            unique.append(term)
        if len(unique) == 2:
            break
    return unique


def bookmark_tag(threshold: int) -> str:
    if type(threshold) is not int or threshold not in BOOKMARK_THRESHOLDS:
        threshold = BOOKMARK_THRESHOLDS[0]
    return f"{threshold}users入り"


def pixiv_search_word(tags: list[str], threshold: int) -> str:
    required = bookmark_tag(threshold)
    terms = [term for term in tags if term and term != required]
    terms.append(required)
    return " ".join(terms)
