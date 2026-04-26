"""
Periodic CAPI retry worker.

Wakes up every `interval_seconds` and asks the CAPIService to drain any
delivery_log rows whose `next_retry_at` is in the past. The work itself
lives in `CAPIService.retry_pending(conn)` — this module is just the
asyncio loop that keeps it on a schedule.

Wired into the FastAPI lifespan in `app/main.py`:

    _capi_retry_worker = start_capi_retry_worker(interval_seconds=300)
    ...
    await _capi_retry_worker.stop()

Operational notes:
  • Uses a fresh DB connection per tick (sqlite3 connections are not
    safe across tasks). The connection is opened inside the loop and
    closed before sleeping — so a hung tick can never leak.
  • Skips work silently if the DB layer raises during a tick — we never
    want a transient failure to take the whole worker offline.
  • Default 300s matches the inner backoff schedule's smallest interval
    (60s / 300s / 1800s), so we never sleep past a due retry by more
    than ~5 minutes on average.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..capi.service import CAPIService, capi_service

logger = logging.getLogger(__name__)


class CAPIRetryWorker:
    """Long-running asyncio task wrapper. Use `start_capi_retry_worker(...)`."""

    def __init__(
        self,
        *,
        service:          CAPIService,
        db_manager,                          # avoid hard import; quack-typed
        interval_seconds: int = 300,
    ) -> None:
        self._service          = service
        self._db_manager       = db_manager
        self._interval_seconds = max(30, int(interval_seconds))
        self._task:    Optional[asyncio.Task[None]] = None
        self._stopping = asyncio.Event()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> "CAPIRetryWorker":
        if self._task is not None and not self._task.done():
            return self
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="capi-retry-worker")
        logger.info(
            "CAPI retry worker started (interval=%ds)",
            self._interval_seconds,
        )
        return self

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
        logger.info("CAPI retry worker stopped")

    # ── Loop ─────────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        # Small startup delay so we don't race the rest of app startup.
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=5)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stopping.is_set():
            try:
                processed = await self._tick()
                if processed:
                    logger.info("CAPI retry worker: processed %d pending row(s)", processed)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Never let a bad tick kill the loop
                logger.exception("CAPI retry worker tick failed: %s", exc)

            try:
                await asyncio.wait_for(
                    self._stopping.wait(),
                    timeout=self._interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> int:
        # Open a short-lived connection per tick.
        with self._db_manager.get_connection() as conn:
            return await self._service.retry_pending(conn)


# ── Factory ──────────────────────────────────────────────────────────────────

def start_capi_retry_worker(
    *,
    interval_seconds: int = 300,
    service:          CAPIService = capi_service,
    db_manager=None,
) -> CAPIRetryWorker:
    """
    Start the worker. `db_manager` defaults to the app's DBManager singleton
    (lazy import to avoid a circular dependency at module load time).
    """
    if db_manager is None:
        from ...database import db_manager as _default_dbm
        db_manager = _default_dbm

    worker = CAPIRetryWorker(
        service          = service,
        db_manager       = db_manager,
        interval_seconds = interval_seconds,
    )
    return worker.start()
