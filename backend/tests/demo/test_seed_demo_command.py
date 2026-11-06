"""The ``flask seed-demo`` command.

The password every demo account signs in with is typed at a hidden prompt, twice,
as ``create-staff-user`` asks for one (ADR-0023), so it never lands in shell history.
The command then lists the accounts and the events it made.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from click.testing import Result
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.services import has_any_users
from app.modules.demo.services import DEMO_ACCOUNTS
from app.modules.events.models import EventRequest

pytestmark = pytest.mark.demo


def _run(app: Flask, password: str) -> Result:
    """Run ``seed-demo``, typing ``password`` at the prompt and again to confirm it."""
    runner = app.test_cli_runner()
    return runner.invoke(args=["seed-demo"], input=f"{password}\n{password}\n")


def test_the_command_lists_every_account_and_event_it_made(
    app: Flask, db_session: Session, password: str
) -> None:
    result = _run(app, password)

    assert result.exit_code == 0, result.output
    for account in DEMO_ACCOUNTS:
        assert f"{account.role.value:<24} {account.email}" in result.output
    for event in db_session.scalars(select(EventRequest)):
        assert f"{event.reference:<14} {event.status.value:<24} {event.name}" in result.output
    assert "Every account's password is the one you typed." in result.output


def test_the_command_refuses_a_database_with_accounts(
    app: Flask, db_session: Session, make_user: Callable[..., User], password: str
) -> None:
    db_session.add(make_user())
    db_session.commit()

    result = _run(app, password)

    assert result.exit_code == 1
    assert "Error: The database already has accounts" in result.output
    assert list(db_session.scalars(select(EventRequest))) == []


def test_the_command_says_why_a_password_was_refused(app: Flask, db_session: Session) -> None:
    result = _run(app, "short")

    assert result.exit_code == 1
    assert "password: " in result.output
    assert has_any_users() is False
