"""Background task management for long-running operations like compress and index."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional


class TaskStatus(str, Enum):
    """Status of a background task."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    """Information about a background task."""

    task_id: str
    path: str
    operation: str  # "compress" or "index"
    status: TaskStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[dict] = None


class TaskManager:
    """Manages background tasks with concurrency control.

    Tracks running tasks to prevent duplicate operations on the same file.
    Automatically cleans up old completed tasks.
    """

    def __init__(self):
        """Initialize the task manager."""
        self._tasks: Dict[str, TaskInfo] = {}  # task_id -> TaskInfo
        self._path_locks: Dict[str, str] = {}  # normalized_path -> task_id
        self._lock = asyncio.Lock()

    async def create_task(self, path: str, operation: str) -> tuple[TaskInfo, bool]:
        """Create a new task if the path is not locked.

        Args:
            path: Normalized file path
            operation: Operation type ("compress" or "index")

        Returns:
            Tuple of (TaskInfo, is_new) where is_new is True if task was created,
            False if a task for this path is already running
        """
        async with self._lock:
            # Check if this path already has an active task
            existing_task_id = self._path_locks.get(path)
            if existing_task_id:
                existing_task = self._tasks.get(existing_task_id)
                if existing_task and existing_task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    return existing_task, False

            # Create new task
            task_id = str(uuid.uuid4())
            task = TaskInfo(
                task_id=task_id,
                path=path,
                operation=operation,
                status=TaskStatus.QUEUED,
                started_at=datetime.now(timezone.utc),
            )

            self._tasks[task_id] = task
            self._path_locks[path] = task_id

            return task, True

    async def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        completed_at: Optional[datetime] = None,
        error: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> None:
        """Update task fields.

        Args:
            task_id: Task ID to update
            status: New status
            completed_at: Completion timestamp
            error: Error message if failed
            result: Result data if completed
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            if status is not None:
                task.status = status
            if completed_at is not None:
                task.completed_at = completed_at
            if error is not None:
                task.error = error
            if result is not None:
                task.result = result

            # Release path lock if task is complete or failed
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                if task.path in self._path_locks and self._path_locks[task.path] == task_id:
                    del self._path_locks[task.path]

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task by ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            TaskInfo if found, None otherwise
        """
        async with self._lock:
            return self._tasks.get(task_id)

    async def cleanup_old_tasks(self, max_age_seconds: int = 3600) -> int:
        """Remove completed/failed tasks older than max_age.

        Args:
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            Number of tasks cleaned up
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            to_remove = []

            for task_id, task in self._tasks.items():
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    if task.completed_at:
                        age = (now - task.completed_at).total_seconds()
                        if age > max_age_seconds:
                            to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]

            return len(to_remove)

    async def get_all_tasks(self) -> list[TaskInfo]:
        """Get all tasks (useful for debugging/monitoring).

        Returns:
            List of all TaskInfo objects
        """
        async with self._lock:
            return list(self._tasks.values())
