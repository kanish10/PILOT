import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class StateStore:
    """
    In-memory task state store.
    Each task gets its own asyncio.Lock to prevent concurrent modifications.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, object] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def create(self, task) -> str:
        async with self._global_lock:
            self._tasks[task.task_id] = task
            self._locks[task.task_id] = asyncio.Lock()
        logger.info("Task %s created", task.task_id)
        return task.task_id

    async def get(self, task_id: str) -> Optional[object]:
        return self._tasks.get(task_id)

    async def lock(self, task_id: str) -> Optional[asyncio.Lock]:
        return self._locks.get(task_id)

    async def delete(self, task_id: str) -> None:
        async with self._global_lock:
            self._tasks.pop(task_id, None)
            self._locks.pop(task_id, None)
        logger.info("Task %s deleted from store", task_id)

    def count(self) -> int:
        return len(self._tasks)


# Singleton used across the app
state_store = StateStore()
