"""进程内任务队列（教学 / 单进程演示用）

限制：
- 不跨进程、不持久化；多实例部署请改用 Celery / ARQ / RQ 等
- 由 lifespan 调用 ``start_queue`` / ``stop_queue``
"""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class MemoryQueue:
    """简单的内存队列实现"""

    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        self._queue: queue.Queue = queue.Queue()
        self._handlers: Dict[str, Callable] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def publish(self, task_type: str, data: Any) -> None:
        """发布任务到队列"""
        self._queue.put((task_type, data))
        logger.debug("Queue publish type=%s", task_type)

    def subscribe(self, task_type: str, handler: Callable) -> None:
        """订阅任务类型"""
        self._handlers[task_type] = handler
        logger.debug("Queue subscribe type=%s", task_type)

    def start(self) -> None:
        """启动队列处理线程"""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker, name="memory-queue-worker", daemon=True
        )
        self._worker_thread.start()
        logger.info("内存队列已启动 (handlers=%s)", list(self._handlers))

    def stop(self, timeout: float = 5.0) -> None:
        """停止队列处理（带超时，避免阻塞关闭）"""
        if not self._running and self._worker_thread is None:
            return
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
            if self._worker_thread.is_alive():
                logger.warning("内存队列工作线程在 %.1fs 内未退出", timeout)
        self._worker_thread = None
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # Python < 3.9 无 cancel_futures
            self._executor.shutdown(wait=False)
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        logger.info("内存队列已停止")

    def _worker(self) -> None:
        while self._running:
            try:
                task_type, data = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                handler = self._handlers.get(task_type)
                if handler is None:
                    logger.warning("无处理器的任务类型: %s", task_type)
                else:
                    self._executor.submit(self._run_handler, task_type, handler, data)
            except Exception as e:
                logger.exception("Queue worker error: %s", e)
            finally:
                self._queue.task_done()

    @staticmethod
    def _run_handler(task_type: str, handler: Callable, data: Any) -> None:
        try:
            handler(data)
        except Exception:
            logger.exception("Queue handler failed type=%s", task_type)


task_queue = MemoryQueue()


def get_queue() -> MemoryQueue:
    return task_queue


async def start_queue() -> None:
    """lifespan 启动钩子"""
    task_queue.start()


async def stop_queue() -> None:
    """lifespan 关闭钩子"""
    task_queue.stop()
