"""Bounded workflow HTTP calls; mutating GETs require the submit policy.

This module does not import the application or load dotenv. Batch replay is only
for import-batch, whose receipt and writes commit in the same DB transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

RETRY_HTTP = {408, 425, 429, 500, 502, 503, 504}
RETRY_TRANSPORT = {5, 6, 7, 18, 28, 35, 52, 55, 56}


@dataclass(frozen=True)
class Reply:
    transport_code: int
    http_status: int
    body: bytes = b''


@dataclass(frozen=True)
class Result:
    state: str
    attempts: int
    http_status: int = 0
    transport_code: int = 0
    reason: str = ''

    @property
    def exit_code(self) -> int:
        if self.state in {
            'succeeded',
            'accepted',
            'running',
            'skipped',
            'not_delivered',
            'not_configured',
            'not_required',
        }:
            return 0
        return 2 if self.state == 'pending_verification' else 1


def is_ready_response(response: object) -> bool:
    return isinstance(response, dict) and response.get('success') is True and response.get('status') == 'ready'


def curl_transport(url: str, *, timeout: float, method: str, headers: dict, body: bytes | None) -> Reply:
    # Do not log the command, URL, stderr or response body: they can hold credentials.
    with tempfile.TemporaryDirectory(prefix='bookrank-http-') as directory:
        response_path = Path(directory, 'response')
        command = [
            'curl',
            '--silent',
            '--show-error',
            '--max-time',
            str(timeout),
            '--connect-timeout',
            str(min(10, timeout)),
            '--max-filesize',
            '2097152',
            '--output',
            str(response_path),
            '--write-out',
            '%{http_code}',
            '--request',
            method,
        ]
        for key, value in headers.items():
            command.extend(['--header', f'{key}: {value}'])
        if body is not None:
            command.extend(['--data-binary', '@-'])
        command.extend(['--url', url])
        try:
            completed = subprocess.run(command, input=body, capture_output=True, timeout=timeout + 1, check=False)
        except subprocess.TimeoutExpired:
            return Reply(28, 0)
        except OSError:
            return Reply(127, 0)
        status = completed.stdout.decode('ascii', errors='ignore').strip()
        return Reply(
            completed.returncode,
            int(status) if status.isdigit() and len(status) == 3 else 0,
            response_path.read_bytes() if response_path.exists() else b'',
        )


def run_request(
    url: str,
    *,
    policy: str = 'read',
    method: str = 'GET',
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: float = 60,
    budget: float = 180,
    attempts: int = 3,
    transport: Callable = curl_transport,
    sleep: Callable = time.sleep,
    clock: Callable = time.monotonic,
) -> Result:
    if not url:
        return Result('not_configured' if policy == 'notify' else 'failed', 0, reason='missing_configuration')
    if policy not in {'read', 'submit', 'batch', 'notify'}:
        raise ValueError('unsupported retry policy')
    if policy == 'read' and method != 'GET':
        raise ValueError('read policy only permits GET')
    if policy == 'batch' and (method != 'POST' or body is None or not url.endswith('/api/new-books/import-batch')):
        raise ValueError('batch replay is restricted to the receipt-protected import endpoint')
    if timeout <= 0 or budget <= 0 or not 1 <= attempts <= 3:
        raise ValueError('positive timeouts and 1-3 attempts required')
    if policy == 'batch':
        payload = json.loads(body)
        if not isinstance(payload, dict) or not payload.get('batch_id'):
            raise ValueError('batch replay requires a fixed batch_id')
    deadline = clock() + budget
    limit = attempts if policy in {'read', 'batch'} else 1
    reply = Reply(28, 0)
    count = 0
    reason = 'budget_exhausted'
    ambiguous_seen = False
    for count in range(1, limit + 1):
        remaining = deadline - clock()
        if remaining <= 0:
            count -= 1
            break
        reply = transport(url, timeout=min(timeout, remaining), method=method, headers=headers or {}, body=body)
        if reply.transport_code == 0 and 200 <= reply.http_status < 300:
            try:
                response = json.loads(reply.body) if reply.body else {}
            except (ValueError, UnicodeError):
                response = None
            if response is None and policy in {'submit', 'batch'}:
                return Result('pending_verification', count, reply.http_status, reason='invalid_acknowledgement')
            if policy == 'read' and (not isinstance(response, dict) or response.get('success') is not True):
                return Result('failed', count, reply.http_status, reason='invalid_readiness_acknowledgement')
            if policy == 'read' and url.rstrip('/').endswith('/health/ready') and not is_ready_response(response):
                return Result('failed', count, reply.http_status, reason='invalid_readiness_acknowledgement')
            if policy == 'submit' and isinstance(response, dict):
                data = response.get('data')
                if isinstance(data, dict) and data.get('status') == 'pending_verification':
                    return Result(
                        'pending_verification', count, reply.http_status, reason='backend_pending_verification'
                    )
                if isinstance(data, dict) and data.get('status') in ('failed', 'partial', 'error'):
                    return Result('failed', count, reply.http_status, reason='backend_task_failure')
            if isinstance(response, dict) and (
                response.get('success') is False
                or (policy == 'notify' and (response.get('code', 0) != 0 or response.get('StatusCode', 0) != 0))
            ):
                return Result(
                    'not_delivered' if policy == 'notify' else ('pending_verification' if ambiguous_seen else 'failed'),
                    count,
                    reply.http_status,
                    reason='business_failure',
                )
            if policy == 'notify':
                # Current senders use Flask APIResponse or Feishu bot receipts.
                # Empty/HTML/204 acknowledgements have no delivery contract here.
                if not isinstance(response, dict):
                    return Result('not_delivered', count, reply.http_status, reason='unrecognized_delivery_receipt')
                codes = [response[key] for key in ('code', 'StatusCode') if key in response]
                valid_codes = all(type(value) in {int, float} and value == 0 for value in codes)
                if not valid_codes or not (response.get('success') is True or codes):
                    return Result('not_delivered', count, reply.http_status, reason='unrecognized_delivery_receipt')
                data = response.get('data')
                if isinstance(data, dict) and 'delivery' in data:
                    delivery = data['delivery']
                    if isinstance(delivery, str) and delivery in {'not_configured', 'not_required', 'not_delivered'}:
                        return Result(delivery, count, reply.http_status, reason='api_delivery_status')
                    if delivery != 'delivered':
                        return Result('not_delivered', count, reply.http_status, reason='unrecognized_delivery_status')
            if policy in {'submit', 'batch'} and (
                not isinstance(response, dict) or response.get('success') is not True
            ):
                return Result('pending_verification', count, reply.http_status, reason='missing_acknowledgement')
            if policy == 'batch':
                receipt = response.get('data')
                if (
                    not isinstance(receipt, dict)
                    or receipt.get('status') not in {'applied', 'duplicate'}
                    or receipt.get('batch_id') != payload['batch_id']
                ):
                    return Result('pending_verification', count, reply.http_status, reason='unmatched_receipt')
            if policy == 'submit' and isinstance(response.get('data'), dict):
                if response['data'].get('status') == 'skipped':
                    return Result('skipped', count, reply.http_status, reason='backend_task_skipped')
                if response['data'].get('status') in ('already_running', 'running'):
                    return Result('running', count, reply.http_status, reason='existing_task_running')
                if response['data'].get('status') == 'completed':
                    return Result('succeeded', count, reply.http_status, reason='backend_task_completed')
            return Result('accepted' if policy == 'submit' else 'succeeded', count, reply.http_status)
        ambiguous_seen = ambiguous_seen or (
            policy in {'submit', 'batch'}
            and (reply.transport_code != 0 or reply.http_status in {408, 425} or reply.http_status >= 500)
        )
        retryable = reply.transport_code in RETRY_TRANSPORT or (
            reply.transport_code == 0 and reply.http_status in RETRY_HTTP
        )
        reason = 'transport_error' if reply.transport_code else 'http_error'
        if not retryable or count == limit:
            break
        delay = min(5 * 2 ** (count - 1), 30)
        if deadline - clock() <= delay:
            reason = 'budget_exhausted'
            break
        sleep(delay)
    unknown = ambiguous_seen
    state = 'not_delivered' if policy == 'notify' else ('pending_verification' if unknown else 'failed')
    return Result(state, count, reply.http_status, reply.transport_code, reason)


def truncate_issue(report: str, run_link: str, limit: int = 12000) -> str:
    footer = f'\n\n完整日志见本次运行的 nyt-frequency-report 产物：{run_link}\n'
    available = max(0, limit - len(footer.encode('utf-8')))
    return report.encode('utf-8')[:available].decode('utf-8', errors='ignore') + footer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', choices=['read', 'submit', 'batch', 'notify'], default='read')
    parser.add_argument('--method', choices=['GET', 'POST'], default='GET')
    parser.add_argument('--url-env', default='BASE_URL')
    parser.add_argument('--path', default='')
    parser.add_argument('--secret-env')
    parser.add_argument('--header-name', default='Authorization')
    parser.add_argument('--body-file', type=Path)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--budget', type=float, default=180)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    headers = {}
    if args.secret_env:
        secret = os.environ.get(args.secret_env, '')
        if not secret:
            result = Result(
                'not_configured' if args.policy == 'notify' else 'failed', 0, reason='missing_auth_configuration'
            )
        else:
            headers[args.header_name] = f'Bearer {secret}' if args.header_name == 'Authorization' else secret
            result = None
    else:
        result = None
    if args.body_file:
        headers['Content-Type'] = 'application/json'
    if args.policy == 'submit' and os.environ.get('GITHUB_RUN_ID'):
        # GitHub keeps RUN_ID on a re-run; RUN_ATTEMPT must not enter this key.
        operation = '\n'.join((os.environ.get('GITHUB_REPOSITORY', ''), os.environ['GITHUB_RUN_ID'], args.path))
        headers['X-Idempotency-Key'] = hashlib.sha256(operation.encode('utf-8')).hexdigest()
    if result is None:
        base = os.environ.get(args.url_env, '').rstrip('/')
        url = base + args.path if base else ''
        result = run_request(
            url,
            policy=args.policy,
            method=args.method,
            headers=headers,
            body=args.body_file.read_bytes() if args.body_file else None,
            timeout=args.timeout,
            budget=args.budget,
        )
    report = json.dumps(asdict(result), ensure_ascii=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report + '\n', encoding='utf-8')
    print(report)
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with Path(summary_path).open('a', encoding='utf-8') as handle:
            handle.write(
                f'HTTP operation: `{result.state}`, attempts={result.attempts}, HTTP={result.http_status}, transport={result.transport_code}.\n\n'
            )
            if result.state == 'pending_verification':
                handle.write('待核实：后端可能已执行，请先查服务器日志或持久回执；不要直接重跑提交。\n\n')
            elif result.state == 'accepted':
                handle.write('仅确认触发请求已被接受；后台任务是否完成仍需服务器日志或关联回执验证。\n\n')
            elif result.state == 'running':
                handle.write('后台任务已在执行；本次没有启动新任务，完成结果仍需服务器日志或关联回执验证。\n\n')
            elif result.state == 'skipped':
                handle.write('本次同步已跳过，没有执行数据刷新；请另行核对来源状态及最后成功时间。\n\n')
            elif result.state == 'not_required':
                handle.write('无需发送告警；API操作完成，不表示已发送通知。\n\n')
            elif result.state in {'not_delivered', 'not_configured'}:
                handle.write('告警未送达；绿色步骤只表示非致命处理完成。\n\n')
    return result.exit_code


if __name__ == '__main__':
    raise SystemExit(main())
