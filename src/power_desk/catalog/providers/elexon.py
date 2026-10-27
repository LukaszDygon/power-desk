"""Elexon definitions provider.

Kinds:
- `datasets/<CODE>`: Insights API dataset summary/description from the OpenAPI spec.
- `glossary/<slug>`: BSC Glossary term. The WordPress REST API locates the term page; the
  page itself carries the plain-language summary (absent from the REST `content` field),
  the formal BSC definition and its BSC section reference.
"""

from __future__ import annotations

import html
import re
from typing import Any

from dlt.sources.helpers import requests

NAME = "elexon"
LABELS = {"datasets": "Elexon Insights API", "glossary": "Elexon BSC Glossary"}

OPENAPI_URL = "https://data.elexon.co.uk/swagger/v1/swagger.json"
API_BASE = "https://data.elexon.co.uk/bmrs/api/v1"
GLOSSARY_API = "https://www.elexon.co.uk/bsc/wp-json/wp/v2/glossary"
HEADERS = {"User-Agent": "PowerDesk/1.0 (data catalogue)"}

# Paragraphs of the OpenAPI descriptions that explain query parameters, not the data.
API_USAGE_NOTES = re.compile(
    r"parameters? must be provided|cannot be set when|filters may be supplied|maximum data output range",
    re.IGNORECASE,
)
GLOSSARY_SECTIONS = ("BSC defined definition", "BSC documentation", "Further information", "Related terms")


def get(url: str, **params: Any) -> requests.Response:
    response = requests.get(url, params=params or None, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response


def clean_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [re.sub(r"\s+", " ", p).strip() for p in paragraphs if p.strip()]


def dataset_definitions(spec: dict[str, Any], codes: list[str]) -> dict[str, dict[str, str]]:
    out = {}
    for code in codes:
        operation = spec["paths"][f"/datasets/{code}"]["get"]
        paragraphs = [p for p in clean_paragraphs(operation.get("description", "")) if not API_USAGE_NOTES.search(p)]
        out[code] = {
            "title": operation.get("summary", code).strip(),
            "summary": "\n\n".join(paragraphs),
            "url": f"{API_BASE}/datasets/{code}",
        }
    return out


def page_text(page_html: str) -> str:
    """Rendered page -> text with paragraph breaks and markdown links."""
    body = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page_html)
    body = re.sub(
        r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        lambda m: f"[{html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()}]({m.group(1)})",
        body,
    )
    body = re.sub(r"(?i)<br\s*/?>|</(p|li|h[1-6]|div|ul|ol)>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def parse_glossary_page(page_html: str, title: str) -> dict[str, str]:
    """Split a glossary page into acronym, summary, definition and reference."""
    text = page_text(page_html)
    heading = f"Glossary Term: {title}"
    start = text.find(heading)
    end = text.find("Suggest content changes", start)
    if start < 0 or end < 0:
        raise ValueError(f"glossary page layout not recognised for {title!r}")
    block = text[start + len(heading):end].strip()

    parts: dict[str, str] = {}
    acronym = re.match(r"Acronym:\s*(\S+)\s*", block)
    if acronym:
        parts["acronym"] = acronym.group(1)
        block = block[acronym.end():]
    pattern = "|".join(re.escape(s) for s in GLOSSARY_SECTIONS)
    pieces = re.split(rf"^({pattern})$", block, flags=re.MULTILINE)
    parts["summary"] = pieces[0].strip()
    for marker, content in zip(pieces[1::2], pieces[2::2]):
        key = {"BSC defined definition": "definition", "BSC documentation": "reference"}.get(marker)
        if key:
            parts[key] = content.strip()
    if parts.get("definition") == parts.get("summary"):
        del parts["definition"]
    return {k: v for k, v in parts.items() if v}


def glossary_term(slug: str) -> dict[str, str]:
    matches = get(GLOSSARY_API, slug=slug, _fields="title,link,modified").json()
    if not matches:
        raise KeyError(f"BSC glossary has no term with slug {slug!r}")
    entry = matches[0]
    title = html.unescape(entry["title"]["rendered"])
    return {
        "title": title,
        **parse_glossary_page(get(entry["link"]).text, title),
        "url": entry["link"],
        "modified": entry["modified"][:10],
    }


def fetch(kind: str, ids: list[str]) -> dict[str, dict[str, str]]:
    """Normalised entries {title, summary, [acronym, definition, reference], url} by id."""
    if kind == "datasets":
        return dataset_definitions(get(OPENAPI_URL).json(), ids)
    if kind == "glossary":
        return {slug: glossary_term(slug) for slug in ids}
    raise KeyError(f"{NAME}: unknown kind {kind!r} (expected one of {sorted(LABELS)})")
