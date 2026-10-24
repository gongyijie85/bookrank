"""Durable, fail-closed receipts for explicitly keyed cron submissions.

The existing system_config primary key arbitrates concurrent claims. Receipts
are retained across restarts; an abandoned accepted/running claim is never
automatically executed again. These receipts do not fence unkeyed callers or
the side effects of a separately scheduled job.
"""

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError

from ..models.database import db
from ..models.schemas import SystemConfig


class ReceiptConflict(ValueError):
    """An existing request key is bound to another operation."""


class ReceiptUnavailable(RuntimeError):
    """An existing receipt cannot be safely interpreted."""


class CronReceipt:
    def __init__(self, key: str, payload: dict[str, Any], encoded: str) -> None:
        self.key = key
        self.payload = payload
        self._encoded = encoded

    @staticmethod
    def _storage_key(request_key: str) -> str:
        if not 1 <= len(request_key) <= 200 or any(not 33 <= ord(char) <= 126 for char in request_key):
            raise ValueError('invalid_idempotency_key')
        return 'cron_receipt:' + hashlib.sha256(request_key.encode()).hexdigest()

    @classmethod
    def read(cls, request_key: str) -> 'CronReceipt | None':
        """Read an existing receipt without claiming, flushing or committing."""
        key = cls._storage_key(request_key)
        with db.session.no_autoflush:
            row = db.session.execute(db.select(SystemConfig.value).where(SystemConfig.key == key)).one_or_none()
        if row is None:
            return None
        encoded = row[0]
        try:
            payload = json.loads(encoded)
            required = ('operation', 'token', 'status', 'accepted_at')
            allowed = {*required, 'observed_at', 'finished_at', 'result'}
            if (
                not isinstance(payload, dict)
                or not set(payload).issubset(allowed)
                or any(not isinstance(payload.get(field), str) or not payload[field] for field in required)
                or payload['status']
                not in ('accepted', 'running', 'completed', 'failed', 'pending_verification', 'skipped')
                or ('result' in payload and not isinstance(payload['result'], dict))
            ):
                raise ReceiptUnavailable('receipt_unavailable')
            for field in ('accepted_at', 'observed_at', 'finished_at'):
                if field in payload:
                    datetime.fromisoformat(payload[field])
        except (TypeError, ValueError) as exc:
            raise ReceiptUnavailable('receipt_unavailable') from exc
        return cls(key, payload, encoded)

    @classmethod
    def claim(cls, request_key: str, operation: str) -> tuple['CronReceipt', bool]:
        key = cls._storage_key(request_key)
        payload: dict[str, Any] = {
            'operation': operation,
            'token': secrets.token_hex(16),
            'status': 'accepted',
            'accepted_at': datetime.now(UTC).isoformat(),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        try:
            db.session.execute(insert(SystemConfig).values(key=key, value=encoded))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = db.session.get(SystemConfig, key)
            if existing is None or not existing.value:
                raise RuntimeError('receipt_unavailable') from None
            stored = json.loads(existing.value)
            if not isinstance(stored, dict) or stored.get('operation') != operation:
                raise ReceiptConflict('idempotency_key_operation_mismatch') from None
            return cls(key, stored, existing.value), True
        except Exception:
            db.session.rollback()
            # COMMIT may have reached the database. Do not execute on an
            # unconfirmed claim; a later request can read the durable receipt.
            raise
        return cls(key, payload, encoded), False

    def transition(self, status: str, result: dict[str, Any] | None = None) -> bool:
        """Compare-and-swap the owned receipt; stale objects cannot publish."""
        updated = dict(self.payload, status=status, observed_at=datetime.now(UTC).isoformat())
        if result is not None:
            updated['result'] = result
        if status in ('completed', 'failed', 'skipped'):
            updated['finished_at'] = datetime.now(UTC).isoformat()
        encoded = json.dumps(updated, ensure_ascii=False, sort_keys=True)
        try:
            changed = db.session.execute(
                update(SystemConfig)
                .where(SystemConfig.key == self.key, SystemConfig.value == self._encoded)
                .values(value=encoded)
                .execution_options(synchronize_session=False)
            ).rowcount
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        if changed != 1:
            return False
        self.payload, self._encoded = updated, encoded
        return True

    def snapshot(self, *, replayed: bool = False) -> dict[str, Any]:
        return {key: value for key, value in self.payload.items() if key != 'token'} | {'replayed': replayed}

    def finish_sync(self, result: dict[str, Any]) -> None:
        status = result.get('status')
        if status in ('failed', 'error', 'partial') or result.get('failed'):
            state = 'failed'
        elif status == 'skipped':
            state = 'skipped'
        elif status in ('synced', 'success', 'complete') and not result.get('failed'):
            state = 'completed'
        else:
            state = 'pending_verification'
        self.transition(state, result)
