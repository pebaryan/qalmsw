"""Retrieval backends for looking up paper metadata.

Default backend is Semantic Scholar (free API, no CAPTCHAs, no auth).
Switch to Google Scholar at runtime via ``set_backend('google-scholar')``
or use the CLI ``--retrieval`` flag.
"""

from qalmsw.retrieval.scholar import ScholarResult
from qalmsw.retrieval.semantic_scholar import search_by_title  # noqa: F401 — re-exported

__all__ = ["ScholarResult", "search_by_title", "set_backend"]


def set_backend(name: str) -> None:
    """Switch the active retrieval backend at runtime.

    This patches the module-level ``search_by_title`` so existing imports
    like ``from qalmsw.retrieval import search_by_title`` pick up the change.

    Parameters
    ----------
    name
        ``'semantic-scholar'`` (default) or ``'google-scholar'``.
    """
    import qalmsw.retrieval as mod

    if name == "google-scholar":
        from qalmsw.retrieval.scholar import search_by_title as _fn
    elif name == "semantic-scholar":
        from qalmsw.retrieval.semantic_scholar import search_by_title as _fn
    else:
        raise ValueError(f"Unknown retrieval backend: {name!r}")
    mod.search_by_title = _fn
