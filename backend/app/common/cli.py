"""What the Flask CLI commands share.

A command turns its options into a service call, like a route does. When the service
refuses with an :class:`~app.common.errors.AppError`, the command shows the error the
way this module renders it.
"""

from __future__ import annotations

from app.common.errors import AppError


def describe_error(error: AppError) -> str:
    """Render an ``AppError`` as the text ``click.ClickException`` shows.

    One line for the error's own message, then one "field: message" line per
    validation detail, so an invalid option or a weak password says exactly what to
    fix.
    """
    lines = [error.message]
    for field, messages in (error.details or {}).items():
        for message in messages:
            lines.append(f"{field}: {message}")
    return "\n".join(lines)
