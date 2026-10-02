# SPDX-License-Identifier: MIT
"""Make the shared test helpers importable under the root pytest (importlib mode)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
