"""Shared helper for formatting the Market Outlook section consistently.

Both the product-investor matcher and the per-pair proposal resolver
pass a market-outlook string through to the LLM.  This module provides
a single formatting function and the API-path constant so behaviour
stays identical no matter which code path is taken.
"""

from __future__ import annotations

# API path used by ``input_loader`` to route market-outlook requests
# through in-memory resolvers (avoids reading from disk).
API_MARKET_OUTLOOK = "api://market_outlook"


def format_market_outlook_section(market_outlook: str | None) -> str:
    """Return a ``# Market Outlook`` markdown section, or a placeholder.

    Parameters
    ----------
    market_outlook : str | None
        Free-form market narrative.  ``None`` or an empty string produce
        the placeholder ``(not provided)``.

    Returns
    -------
    str
        A ``# Market Outlook`` heading followed by the narrative or the
        placeholder, separated by a blank line.
    """
    heading = "# Market Outlook"
    body = market_outlook.strip() if market_outlook else "(not provided)"
    return f"{heading}\n\n{body}"


def resolve_market_outlook(
    market_outlook: str | None,
    market_outlook_source: str | None = None,
    default_source: str = "request",
) -> str | None:
    """Return the effective market-outlook string given the source selection.

    Precedence: ``market_outlook_source`` (request) → ``default_source`` (yaml)
    → ``"request"``.

    - ``"static"`` → always ``None`` (the caller loads the static default glob).
    - ``"request"`` (or any other value) → return ``market_outlook`` as-is; the
      caller falls back to the static default when it is ``None``.
    """
    chosen = str(market_outlook_source or default_source or "request").strip()
    if chosen == "static":
        return None
    return market_outlook
