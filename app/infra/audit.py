# app/infra/audit.py
"""Simple audit logging utility."""

import logging

log = logging.getLogger("app.audit")


def audit(event: str, **fields) -> None:
    """Log an audit event.

    The message is built in the format ``event|key1=val1|key2=val2`` and
    emitted using the global logging configuration.

    Args:
        event: Name of the audited event.
        **fields: Additional key/value pairs to include in the log.
    """
    parts = [event]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    log.info("|".join(parts))