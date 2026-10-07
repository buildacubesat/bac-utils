# SPDX-License-Identifier: MIT
"""Build a CubeSat – assembly pricing.

``engine`` is the pure computation (multi-level BOM rollup, batch waterfall,
regional prices), ``store`` the pricing engine's tables and files in the
suite's database, ``notebook`` the marimo UI over both, ``cli`` the
``bac-pricing`` launcher. The suite shell finds the notebook through
:data:`APP` (entry-point group ``bac_suite.apps``).
"""

from pathlib import Path

__version__ = "1.4.0"

NOTEBOOK = Path(__file__).with_name("notebook.py")
APP = {"label": "Pricing", "route": "/pricing", "notebook": NOTEBOOK}
