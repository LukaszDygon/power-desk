"""The dbt catalogue: definitions, provider snapshots and the dbt sources and doc blocks generated from them."""


class CatalogError(ValueError):
    """A definition, reference or raw schema the catalogue cannot resolve."""
