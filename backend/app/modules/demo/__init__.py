"""Demo module — seed data for walking through ConnectSphere.

``flask seed-demo`` fills an empty database with an account for every role, two
client organisations, venues, equipment, and events at each stage a walkthrough
needs. It has no routes and no tables of its own: everything it makes goes through
the other modules' services, so the data obeys the same rules a user's would.

Public surface:

* :func:`app.modules.demo.services.seed_demo`
* :data:`app.modules.demo.services.DEMO_ACCOUNTS`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Add the ``seed-demo`` command to ``app``."""
    from app.modules.demo.commands import seed_demo_command

    app.cli.add_command(seed_demo_command)
