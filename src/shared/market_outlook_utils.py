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
