from __future__ import annotations

import time
import uuid
from threading import Event

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import COMPUTE_TASK_PARALLELISM
from app.database.session import SessionLocal
from app.market_data.provider import close_process_market_provider

from .handlers.production import register_production_handlers
from .runner import (
    acquire_worker_lease,
    recover_interrupted_tasks,
    release_worker_lease,
    run_next_task,
    start_lease_heartbeat,
)


def run_worker(
    *,
    session_factory: sessionmaker[Session] = SessionLocal,
    idle_timeout_seconds: float = 60,
    poll_interval_seconds: float = 1,
    lease_wait_seconds: float = 2,
    compute_parallelism: int = COMPUTE_TASK_PARALLELISM,
) -> bool:
    owner_id = str(uuid.uuid4())
    lease_deadline = time.monotonic() + lease_wait_seconds
    while not acquire_worker_lease(session_factory, owner_id):
        if time.monotonic() >= lease_deadline:
            return False
        time.sleep(min(0.1, poll_interval_seconds))
    stop = Event()
    heartbeat = start_lease_heartbeat(session_factory, owner_id, stop)
    try:
        with session_factory() as db:
            recover_interrupted_tasks(db)
        idle_since = time.monotonic()
        while True:
            if stop.is_set():
                return False
            if run_next_task(session_factory, compute_parallelism=compute_parallelism):
                idle_since = time.monotonic()
                continue
            if time.monotonic() - idle_since >= idle_timeout_seconds:
                return True
            time.sleep(poll_interval_seconds)
    finally:
        close_process_market_provider()
        stop.set()
        heartbeat.join(timeout=2)
        release_worker_lease(session_factory, owner_id)


def main() -> None:
    register_production_handlers()
    run_worker()


if __name__ == "__main__":
    main()
