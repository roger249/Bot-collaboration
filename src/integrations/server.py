"""
DEPRECATED — use ``data_server`` or ``proposal_server`` instead.

This module exists only for backward compatibility.  For new code:

- Import ``app`` from ``src.integrations.data_server`` for client/product APIs.
- Import ``app`` from ``src.integrations.proposal_server`` for reinvestment proposal APIs.
- Import proposal functions from ``src.integrations.reinvestment_proposal`` directly.

The ``app`` re-exported here is ``data_server.app`` and does **not** include
proposal routes.  If you need the proposal routes in a TestClient, use
``proposal_server.app``.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "src.integrations.server is deprecated. Use data_server or proposal_server instead.",
    DeprecationWarning,
    stacklevel=2,
)

from src.integrations.data_server import app  # noqa: E402, F401
from src.integrations.reinvestment_proposal import (  # noqa: E402, F401
    propose_reinvestment,
    propose_reinvestment_for_maturing_holdings,
)
