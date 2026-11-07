"""Alerts for the repo owner, behind an interface so the provider can change.

Only a logging notifier exists for now. The Discord webhook provider gets its own ADR.
Alert text follows the logging rules: no secrets, emails or payment data.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

logger = logging.getLogger(__name__)


class Severity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Alert:
    severity: Severity
    title: str
    detail: str


class Notifier(Protocol):
    def send(self, alert: Alert) -> None: ...


class LoggingNotifier:
    """Writes alerts to the log, where an operator or log alerting picks them up."""

    def send(self, alert: Alert) -> None:
        level = logging.ERROR if alert.severity is Severity.ERROR else logging.WARNING
        logger.log(level, "ALERT %s: %s", alert.title, alert.detail)
