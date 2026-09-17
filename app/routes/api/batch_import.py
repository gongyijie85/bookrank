"""Batch import HTTP endpoint (issue #134).

Uses BATCH_IMPORT_SECRET only — never CRON_SECRET — so crawl jobs cannot write.
"""

from __future__ import annotations

from flask import request

from ...services.batch_import_service import BatchImportError, import_batch
from ...utils.api_helpers import APIResponse, handle_api_errors, rate_limit
from . import _verify_bearer, api_bp


@api_bp.route('/new-books/import-batch', methods=['POST'])
@rate_limit(max_requests=60, window=60)
@handle_api_errors
def import_new_books_batch() -> tuple:
    """接收单社采集批次并幂等入库。"""
    if not _verify_bearer('BATCH_IMPORT_SECRET'):
        return APIResponse.error('Unauthorized', 401)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return APIResponse.error(
            'Invalid JSON body',
            400,
            errors={'code': 'SCHEMA_INVALID'},
        )

    try:
        result = import_batch(payload)
    except BatchImportError as exc:
        return APIResponse.error(
            exc.message,
            exc.status_code,
            errors={'code': exc.code},
        )

    return APIResponse.success(data=result.receipt, message=result.status)
