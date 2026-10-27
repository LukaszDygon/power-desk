"""Definition providers: fetch official definitions for catalogue references.

A reference is `<provider>:<kind>/<id>`.
A provider module exposes:
- `NAME`: provider key used in references
- `LABELS`: {kind: human label shown in the docs}
- `fetch(kind, ids) -> {id: {title, summary, url, [acronym, definition, reference, modified]}}`
Register new providers (e.g. for another data publisher's code lists) in `PROVIDERS`.
"""

from types import ModuleType

from power_desk.catalog.providers import elexon, entsoe

PROVIDERS: dict[str, ModuleType] = {p.NAME: p for p in (elexon, entsoe)}


def parse_ref(ref: str) -> tuple[str, str, str]:
    """`provider:kind/id` -> (provider, kind, id)."""
    try:
        provider, path = ref.split(":", 1)
        kind, ident = path.split("/", 1)
    except ValueError:
        raise ValueError(f"bad reference {ref!r}; expected <provider>:<kind>/<id>") from None
    if provider not in PROVIDERS:
        raise KeyError(f"unknown definitions provider {provider!r} in {ref!r}; known: {sorted(PROVIDERS)}")
    return provider, kind, ident
