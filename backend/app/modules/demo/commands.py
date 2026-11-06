"""Flask CLI command for the demo module.

A command stays thin, like a route: take the password, call the service, echo what it
made. The work happens in ``services.py``, never here.
"""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from app.common.cli import describe_error
from app.common.errors import AppError
from app.modules.demo.services import DEMO_ACCOUNTS, seed_demo


@click.command("seed-demo")
@with_appcontext
def seed_demo_command() -> None:
    """Fill an empty database with demo accounts and events.

    The password every demo account signs in with is prompted for twice, hidden, as
    ``create-staff-user`` does (ADR-0023), so it never lands in shell history. A
    database that already has an account is refused.
    """
    password = click.prompt(
        "Password for every demo account", hide_input=True, confirmation_prompt=True
    )

    try:
        events = seed_demo(password)
    except AppError as exc:
        raise click.ClickException(describe_error(exc)) from exc

    click.echo("Accounts:")
    for account in DEMO_ACCOUNTS:
        click.echo(f"  {account.role.value:<24} {account.email}")
    click.echo("Events:")
    for event in events:
        click.echo(f"  {event.reference:<14} {event.status:<24} {event.name}")
    click.echo("Every account's password is the one you typed.")
