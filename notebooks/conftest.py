# SPDX-License-Identifier: MIT
"""Make `notebook_harness` importable for every notebook's tests under the root pytest (importlib mode)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
