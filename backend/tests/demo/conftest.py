"""Fixtures for the demo seed's tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture()
def password(valid_registration_payload: dict[str, Any]) -> str:
    """A password the policy accepts, typed for every demo account (ADR-0005)."""
    return valid_registration_payload["password"]
