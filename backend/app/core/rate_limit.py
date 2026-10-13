import time
from typing import Dict, List, Optional
from threading import Lock
from fastapi import HTTPException, Request, status

class InMemoryRateLimiter:
    """
    Lightweight, dependency-free, in-process sliding-window rate limiter.
    
    IMPORTANT ARCHITECTURAL LIMITATIONS:
    1. IN-PROCESS ONLY: State is maintained strictly within the current Python
       process memory. In multi-worker deployments (e.g. Uvicorn with multiple workers)
       or across multiple server instances, each process maintains its own independent
       counter. Distributed rate-limiting across clusters requires an external store (e.g. Redis).
    2. REVERSE PROXY IP HANDLING: Uses request.client.host directly to avoid blind trust
       in spoofed X-Forwarded-For headers. If deployed behind a trusted reverse proxy,
       the reverse proxy should either enforce rate limiting at the edge (recommended)
       or properly overwrite the client address.
    """

    def __init__(
        self,
        requests_limit: int = 15,
        window_seconds: int = 60,
        max_tracked_ips: int = 10000,
        enabled: bool = True,
    ):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.max_tracked_ips = max_tracked_ips
        self.enabled = enabled
        self._records: Dict[str, List[float]] = {}
        # FastAPI sync endpoints may run concurrently in multiple threads.
        self._lock = Lock()

    def check(self, request: Request) -> None:
        """Atomically enforce the per-IP sliding window in one Python process."""
        if not self.enabled:
            return

        client_host = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds

        # The lock prevents simultaneous requests from bypassing the limit
        # by all observing the same number of timestamps before insertion.
        with self._lock:
            timestamps = self._records.get(client_host, [])
            valid_timestamps = [t for t in timestamps if t > window_start]

            if len(valid_timestamps) >= self.requests_limit:
                oldest_timestamp = valid_timestamps[0]
                retry_after = max(1, int(oldest_timestamp + self.window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            valid_timestamps.append(now)
            self._records[client_host] = valid_timestamps

            if len(self._records) > self.max_tracked_ips:
                self._prune_memory(now)

    def _prune_memory(self, now: float) -> None:
        """Prune expired entries across all records to bound memory usage."""
        window_start = now - self.window_seconds
        keys_to_remove = [
            ip for ip, times in self._records.items()
            if not times or times[-1] <= window_start
        ]
        for ip in keys_to_remove:
            self._records.pop(ip, None)

    def reset(self) -> None:
        """Reset internal rate limit tracking state (primarily for test isolation)."""
        with self._lock:
            self._records.clear()


# Pre-configured instances for auth endpoints
auth_rate_limiter = InMemoryRateLimiter(
    requests_limit=15,
    window_seconds=60,
    max_tracked_ips=10000,
)
