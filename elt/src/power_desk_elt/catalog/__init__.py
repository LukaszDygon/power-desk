"""The dbt catalogue: definitions, provider snapshots, and the dbt sources, docs and contracts made from them."""


class CatalogError(ValueError):
    """A definition, reference or raw schema the catalogue cannot resolve."""
