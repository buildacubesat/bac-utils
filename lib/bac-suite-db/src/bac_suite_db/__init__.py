# SPDX-License-Identifier: MIT
"""Shared PostgreSQL layer of the Build a CubeSat business operations suite.

One database, several engines. This package owns what every engine shares:
the ``bac.items`` and ``bac.catalog`` tables, the connection and its
bootstrap config, the SKU scheme, and the ``bac-db`` command that creates
the schema and moves data between the database and the engines' files.
Engines register themselves through the ``bac_suite.engines`` entry-point
group (see :mod:`bac_suite_db.schema`).
"""

__version__ = "0.1.0"
