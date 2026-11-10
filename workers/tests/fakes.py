"""Fakes shared by agent tests."""

from dataclasses import dataclass, field

from pipeline.notify import Alert


@dataclass
class FakeNotifier:
    alerts: list[Alert] = field(default_factory=list)

    def send(self, alert: Alert) -> None:
        self.alerts.append(alert)
