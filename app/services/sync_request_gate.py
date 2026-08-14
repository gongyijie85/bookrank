"""同步请求闸门（sync request gate）：同步冷却、多 worker 锁、per-IP 导出冷却与静态播种一次性化。

（候选 #5）这些状态此前散落在 routes/new_books.py 的 current_app.extensions
裸键上；收敛到本模块，由 app.setup.init_services 注册为
app.extensions['sync_request_gate']。无外部依赖，可独立测试。
"""

import threading
import time

_SYNC_COOLDOWN_SECONDS = 60.0
_EXPORT_COOLDOWN_SECONDS = 10.0


class SyncRequestGate:
    """应用级同步请求状态闸门。"""

    def __init__(self) -> None:
        self._sync_lock = threading.Lock()
        self._last_sync_at = 0.0
        self._export_last_at: dict[str, float] = {}
        self._seed_lock = threading.Lock()
        self._seed_done = False

    def reset(self) -> None:
        """复位全部状态（测试与生命周期复位用）。"""
        with self._sync_lock:
            self._last_sync_at = 0.0
        self._export_last_at = {}
        with self._seed_lock:
            self._seed_done = False

    # ---- 同步冷却 ----

    def sync_cooldown_remaining(self) -> float | None:
        """返回剩余冷却秒数；不在冷却期返回 None。"""
        with self._sync_lock:
            elapsed = time.time() - self._last_sync_at
            if elapsed < _SYNC_COOLDOWN_SECONDS:
                return _SYNC_COOLDOWN_SECONDS - elapsed
            return None

    def record_sync(self) -> None:
        """记录一次同步完成时间（多 worker 安全）。"""
        with self._sync_lock:
            self._last_sync_at = time.time()

    # ---- per-IP 导出冷却 ----

    def export_cooldown_remaining(self, ip: str) -> float | None:
        """返回该 IP 的剩余导出冷却秒数；不在冷却期返回 None 并记录本次访问。

        每次访问顺带惰性清理已过期条目，字典有界。
        """
        now = time.time()
        self._export_last_at = {k: v for k, v in self._export_last_at.items() if now - v < _EXPORT_COOLDOWN_SECONDS}
        last = self._export_last_at.get(ip)
        if last is not None and now - last < _EXPORT_COOLDOWN_SECONDS:
            return _EXPORT_COOLDOWN_SECONDS - (now - last)
        self._export_last_at[ip] = now
        return None

    # ---- 静态播种一次性化 ----

    def seed_static_data(self, sync_engine) -> None:
        """进程内只执行一次静态数据兜底播种（幂等：首个请求执行，后续跳过）。"""
        with self._seed_lock:
            if self._seed_done:
                return
            sync_engine.ensure_static_data_seeded()
            self._seed_done = True
