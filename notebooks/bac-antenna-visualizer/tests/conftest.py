# SPDX-License-Identifier: MIT
"""Make the notebook importable under the root pytest (importlib mode)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
