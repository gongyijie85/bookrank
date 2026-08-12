"""Batch import HTTP endpoint (issue #134).

Uses BATCH_IMPORT_SECRET only — never CRON_SECRET — so crawl jobs cannot write.
"""

from __future__ import annotations

import logging
import secrets

from flask import current_app, request

from ...services.batch_import_service import BatchImportError, import_batch
from ...utils.api_helpers import APIResponse, handle_api_errors
from . import api_bp

logger = logging.getLogger(__name__)


def _verify_batch_import_secret() -> bool:
    secret = current_app.config.get('BATCH_IMPORT_SECRET') or ''
    if not secret:
        logger.warning('BATCH_IMPORT_SECRET 未配置，拒绝批次导入请求')
        return False
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    token = auth_header[7:]
    return secrets.compare_digest(token, secret)


@api_bp.route('/new-books/import-batch', methods=['POST'])
@handle_api_errors
def import_new_books_batch() -> tuple:
    """接收单社采集批次并幂等入库。"""
    if not _verify_batch_import_secret():
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
