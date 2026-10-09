# SPDX-License-Identifier: MIT
"""Build a CubeSat – business operations suite shell.

The orchestrated run mode of the suite concept (§2.1): one web app with
every engine's notebook behind a common index, all on the same database.
It holds no logic of its own; engines register their notebook under the
``bac_suite.apps`` entry-point group and appear here as soon as they are
installed.
"""

__version__ = "0.2.1"
