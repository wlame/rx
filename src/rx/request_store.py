"""In-memory storage for request tracking.

This module provides thread-safe storage for tracking trace request details.
Requests are stored in memory and can be retrieved by request_id.

Note: This is an in-memory store. Data is lost when the process restarts.
For persistent storage, a database backend would be needed.
"""

from datetime import datetime
from threading import Lock
from typing import Optional

from rx.models import RequestInfo

# Thread-safe request store
_requests: dict[str, RequestInfo] = {}
_lock = Lock()

# Maximum number of requests to keep in memory (to prevent memory leaks)
MAX_STORED_REQUESTS = 100000


def store_request(info: RequestInfo) -> None:
    """
    Store a request in the in-memory store.

    Args:
        info: RequestInfo object to store
    """
    with _lock:
        # If we're at capacity, remove oldest completed requests
        if len(_requests) >= MAX_STORED_REQUESTS:
            _cleanup_oldest_completed()
        _requests[info.request_id] = info


def get_request(request_id: str) -> Optional[RequestInfo]:
    """
    Get a request by its ID.

    Args:
        request_id: The request ID to look up

    Returns:
        RequestInfo if found, None otherwise
    """
    with _lock:
        return _requests.get(request_id)


def update_request(request_id: str, **kwargs) -> bool:
    """
    Update fields of a stored request.

    Args:
        request_id: The request ID to update
        **kwargs: Fields to update

    Returns:
        True if request was found and updated, False otherwise
    """
    with _lock:
        if request_id in _requests:
            for key, value in kwargs.items():
                if hasattr(_requests[request_id], key):
                    setattr(_requests[request_id], key, value)
            return True
        return False


def increment_hook_counter(request_id: str, event_type: str, success: bool) -> None:
    """
    Increment hook call counter for a request.

    Args:
        request_id: The request ID
        event_type: 'on_file', 'on_match', or 'on_complete'
        success: Whether the hook call succeeded
    """
    with _lock:
        if request_id not in _requests:
            return

        info = _requests[request_id]
        if event_type == 'on_file':
            if success:
                info.hook_on_file_success += 1
            else:
                info.hook_on_file_failed += 1
        elif event_type == 'on_match':
            if success:
                info.hook_on_match_success += 1
            else:
                info.hook_on_match_failed += 1
        elif event_type == 'on_complete':
            if success:
                info.hook_on_complete_success += 1
            else:
                info.hook_on_complete_failed += 1


def list_requests(limit: int = 100, include_completed: bool = True) -> list[dict]:
    """
    List stored requests.

    Args:
        limit: Maximum number of requests to return
        include_completed: Whether to include completed requests

    Returns:
        List of request info dictionaries
    """
    with _lock:
        requests = list(_requests.values())

    if not include_completed:
        requests = [r for r in requests if r.completed_at is None]

    # Sort by started_at descending (most recent first)
    requests.sort(key=lambda r: r.started_at, reverse=True)

    return [r.model_dump(mode='json') for r in requests[:limit]]


def clear_old_requests(max_age_seconds: int = 3600) -> int:
    """
    Remove requests older than max_age_seconds.

    Args:
        max_age_seconds: Maximum age in seconds for completed requests

    Returns:
        Number of requests removed
    """
    with _lock:
        now = datetime.now()
        to_remove = []

        for rid, info in _requests.items():
            if info.completed_at:
                age = (now - info.completed_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(rid)

        for rid in to_remove:
            del _requests[rid]

        return len(to_remove)


def _cleanup_oldest_completed() -> None:
    """
    Remove oldest completed requests to make room for new ones.
    Must be called with _lock held.
    """
    # Get completed requests sorted by completion time
    completed = [(rid, info) for rid, info in _requests.items() if info.completed_at is not None]
    completed.sort(key=lambda x: x[1].completed_at)

    # Remove oldest 10% or at least 100 requests
    to_remove = max(len(completed) // 10, min(100, len(completed)))

    for rid, _ in completed[:to_remove]:
        del _requests[rid]


def get_store_stats() -> dict:
    """
    Get statistics about the request store.

    Returns:
        Dictionary with store statistics
    """
    with _lock:
        total = len(_requests)
        completed = sum(1 for r in _requests.values() if r.completed_at is not None)
        in_progress = total - completed

        return {
            'total_requests': total,
            'completed_requests': completed,
            'in_progress_requests': in_progress,
            'max_capacity': MAX_STORED_REQUESTS,
        }
