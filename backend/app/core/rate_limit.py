import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status

_locks = Lock()
_stores: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
    detail: str = "Rate limit exceeded. Please try again later.",
) -> None:
    now = time.time()
    with _locks:
        window = _stores[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
            )
        window.append(now)


def reset_rate_limits() -> None:
    with _locks:
        _stores.clear()
