"""Structured JSON logging + optional external analytics sink.

Two problems in the original code this fixes:
  1. Failures were never logged anywhere the developer could see -- only
     successful completions were pushed to the Google Sheet webhook, so
     an outage looked identical to "nobody's using it".
  2. There was no way to correlate a single user's request across
     parsing -> LLM call -> render.

``StructuredLogger`` always emits JSON lines to stdout (which Streamlit
Community Cloud, Docker, or any log aggregator can pick up) regardless of
whether an external webhook is configured. The webhook becomes an
optional, additional sink for the lightweight usage dashboard -- not the
only record that anything happened.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

import requests


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger("careerreshape")
    if root.handlers:
        return  # idempotent -- Streamlit reruns the script on every interaction
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


class AnalyticsSink(Protocol):
    def send(self, event_type: str, details: dict[str, Any]) -> None: ...
    def summary(self) -> dict[str, Any] | None: ...


class NullAnalyticsSink:
    def send(self, event_type: str, details: dict[str, Any]) -> None:
        return

    def summary(self) -> dict[str, Any] | None:
        return None


class WebhookAnalyticsSink:
    """Fire-and-forget usage events to a Google Apps Script webhook.

    Never raises -- a misconfigured or unreachable webhook must never
    break the user-facing flow. Failures here go to the structured log
    instead of vanishing silently, unlike the original implementation.
    """

    def __init__(self, webhook_url: str, *, timeout_seconds: float = 3.0) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout_seconds
        self._logger = logging.getLogger("careerreshape.analytics")

    def send(self, event_type: str, details: dict[str, Any]) -> None:
        try:
            requests.post(
                self._webhook_url,
                json={"event_type": event_type, "details": details},
                timeout=self._timeout,
            )
        except Exception:
            self._logger.warning("analytics.webhook_send_failed", exc_info=True)

    def summary(self) -> dict[str, Any] | None:
        try:
            response = requests.get(self._webhook_url, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception:
            self._logger.warning("analytics.webhook_summary_failed", exc_info=True)
            return None


class StructuredLogger:
    """A thin per-request logger: attaches a trace_id to every event so a
    single optimization request's start/completion/failure lines can be
    grep'd together, and forwards success/failure events to the
    analytics sink."""

    def __init__(self, sink: AnalyticsSink | None = None) -> None:
        self._logger = logging.getLogger("careerreshape.app")
        self._sink = sink or NullAnalyticsSink()
        self.trace_id = uuid.uuid4().hex[:12]

    def _log(self, level: int, event: str, **fields: Any) -> None:
        fields = {"trace_id": self.trace_id, **fields}
        self._logger.log(level, event, extra={"extra_fields": fields})

    def info(self, event: str, **fields: Any) -> None:
        self._log(logging.INFO, event, **fields)
        if event.endswith(".completed") or event == "page_view":
            self._sink.send(event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._log(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._log(logging.ERROR, event, **fields)
        self._sink.send(event, fields)  # failures matter for the dashboard too

    def usage_summary(self) -> dict[str, Any] | None:
        return self._sink.summary()
