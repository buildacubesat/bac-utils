# SPDX-License-Identifier: MIT
"""Make the notebook and the test helper importable under the root pytest (importlib mode)."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))  # the notebook
sys.path.insert(0, str(_HERE))  # visualizer_testkit
