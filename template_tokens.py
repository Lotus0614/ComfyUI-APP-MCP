"""In-memory access tokens for template execution."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


_TOKEN_STORE_MAX = 4096
_RECOVERY_INSTRUCTION = (
    "Call get_template to read the current template information and obtain a new token."
)


@dataclass
class _TokenRecord:
    token: str
    template_name: str
    schema_revision: str
    created_at: float
    expires_at: float
    max_uses: int
    ttl_seconds: float
    uses: int = 0
    reservations: set[str] = field(default_factory=set)


class TemplateTokenStore:
    """Issue and atomically account for bounded template execution tokens."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        token_factory: Callable[[], str] | None = None,
        max_entries: int = _TOKEN_STORE_MAX,
    ) -> None:
        self._clock = clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._max_entries = max_entries
        self._records: dict[str, _TokenRecord] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _expires_at_text(timestamp: float) -> str:
        value = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        return value.replace("+00:00", "Z")

    @staticmethod
    def _recovery(template_name: str) -> dict:
        return {
            "tool": "get_template",
            "arguments": {"name": template_name},
            "instruction": _RECOVERY_INSTRUCTION,
        }

    def _error(self, code: str, message: str, template_name: str) -> dict:
        return {
            "error_code": code,
            "error": f"{message} {_RECOVERY_INSTRUCTION}",
            "template": template_name,
            "recovery": self._recovery(template_name),
        }

    def _trim_locked(self) -> None:
        while len(self._records) >= self._max_entries:
            self._records.pop(next(iter(self._records)))

    def issue(
        self,
        template_name: str,
        schema_revision: str,
        *,
        max_uses: int,
        ttl_seconds: float,
    ) -> dict:
        now = self._clock()
        with self._lock:
            token = self._token_factory()
            while token in self._records:
                token = self._token_factory()
            record = _TokenRecord(
                token=token,
                template_name=template_name,
                schema_revision=schema_revision,
                created_at=now,
                expires_at=now + ttl_seconds,
                max_uses=max_uses,
                ttl_seconds=ttl_seconds,
            )
            self._trim_locked()
            self._records[token] = record
        return {
            "template_token": token,
            "template_token_expires_at": self._expires_at_text(record.expires_at),
            "template_token_max_uses": max_uses,
        }

    def _validate_locked(
        self,
        token: str | None,
        template_name: str,
        schema_revision: str,
        *,
        max_uses: int,
        ttl_seconds: float,
    ) -> tuple[_TokenRecord | None, dict | None]:
        if token is None or token == "":
            return None, self._error(
                "TEMPLATE_TOKEN_REQUIRED",
                "A template token is required.",
                template_name,
            )
        if not isinstance(token, str):
            return None, self._error(
                "TEMPLATE_TOKEN_INVALID",
                "The template token must be a string.",
                template_name,
            )

        record = self._records.get(token)
        if record is None:
            return None, self._error(
                "TEMPLATE_TOKEN_INVALID",
                "The template token is invalid.",
                template_name,
            )
        if record.template_name != template_name:
            return None, self._error(
                "TEMPLATE_TOKEN_WRONG_TEMPLATE",
                f"The template token belongs to '{record.template_name}', not '{template_name}'.",
                template_name,
            )
        if (
            record.schema_revision != schema_revision
            or record.max_uses != max_uses
            or record.ttl_seconds != ttl_seconds
        ):
            return None, self._error(
                "TEMPLATE_TOKEN_STALE",
                "The template or token policy has changed.",
                template_name,
            )
        if self._clock() >= record.expires_at:
            return None, self._error(
                "TEMPLATE_TOKEN_EXPIRED",
                "The template token has expired.",
                template_name,
            )
        if record.uses + len(record.reservations) >= record.max_uses:
            return None, self._error(
                "TEMPLATE_TOKEN_EXHAUSTED",
                "The template token has reached its execution limit.",
                template_name,
            )
        return record, None

    def validate(
        self,
        token: str | None,
        template_name: str,
        schema_revision: str,
        *,
        max_uses: int,
        ttl_seconds: float,
    ) -> dict | None:
        with self._lock:
            _, error = self._validate_locked(
                token,
                template_name,
                schema_revision,
                max_uses=max_uses,
                ttl_seconds=ttl_seconds,
            )
            return error

    def reserve(
        self,
        token: str | None,
        template_name: str,
        schema_revision: str,
        *,
        max_uses: int,
        ttl_seconds: float,
    ) -> tuple[str | None, dict | None]:
        with self._lock:
            record, error = self._validate_locked(
                token,
                template_name,
                schema_revision,
                max_uses=max_uses,
                ttl_seconds=ttl_seconds,
            )
            if error:
                return None, error
            reservation_id = secrets.token_urlsafe(16)
            record.reservations.add(reservation_id)
            return reservation_id, None

    def commit(self, token: str, reservation_id: str) -> dict:
        with self._lock:
            record = self._records.get(token)
            if record is None or reservation_id not in record.reservations:
                return {}
            record.reservations.remove(reservation_id)
            record.uses += 1
            return {
                "template_token_remaining_uses": max(
                    record.max_uses - record.uses,
                    0,
                ),
                "template_token_expires_at": self._expires_at_text(record.expires_at),
            }

    def release(self, token: str | None, reservation_id: str | None) -> None:
        if not token or not reservation_id:
            return
        with self._lock:
            record = self._records.get(token)
            if record is not None:
                record.reservations.discard(reservation_id)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


template_token_store = TemplateTokenStore()
