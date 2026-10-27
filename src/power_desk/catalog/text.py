"""Plain-text summaries of rendered (markdown) descriptions, for listings and graph labels."""

from __future__ import annotations

import re


def plain_summary(description: str | None, paragraphs: int = 2) -> str:
    blocks = [block for block in re.split(r"\n\s*\n", description or "") if block.strip()]
    text = " ".join(blocks[:paragraphs])
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", text)).strip()
