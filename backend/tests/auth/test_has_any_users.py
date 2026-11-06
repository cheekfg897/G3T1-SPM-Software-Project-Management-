"""Whether the database holds any account yet.

The demo seed (``flask seed-demo``) runs only on a database with no accounts, so it
can never mix demo data into real data. It asks the auth module through this check.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.services import has_any_users

pytestmark = pytest.mark.demo


def test_an_empty_database_has_no_users(db_session: Session) -> None:
    assert has_any_users() is False


def test_a_database_with_one_account_has_users(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    db_session.add(make_user())
    db_session.commit()

    assert has_any_users() is True
