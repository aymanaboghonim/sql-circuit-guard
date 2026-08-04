"""In-memory Token Bucket rate limiter for cloud API fallback calls."""

import time
from dataclasses import dataclass


@dataclass
class TokenBucket:
    """Token bucket configuration for API rate limits."""

    capacity: int
    fill_rate_per_sec: float
    tokens: float
    last_update: float


class GateRateLimiter:
    """Manages RPM and TPM limits to prevent Cloud API 429 exceptions."""

    def __init__(self, max_rpm: int = 10, max_tpm: int = 200_000) -> None:
        now = time.monotonic()
        # Requests per minute bucket
        self.rpm_bucket = TokenBucket(
            capacity=max_rpm,
            fill_rate_per_sec=max_rpm / 60.0,
            tokens=float(max_rpm),
            last_update=now,
        )
        # Tokens per minute bucket
        self.tpm_bucket = TokenBucket(
            capacity=max_tpm,
            fill_rate_per_sec=max_tpm / 60.0,
            tokens=float(max_tpm),
            last_update=now,
        )

    def _refill(self, bucket: TokenBucket, now: float) -> None:
        """Refill bucket tokens based on elapsed time."""
        elapsed = now - bucket.last_update
        bucket.tokens = min(
            float(bucket.capacity), bucket.tokens + elapsed * bucket.fill_rate_per_sec
        )
        bucket.last_update = now

    def acquire(self, estimated_tokens: int = 1000) -> bool:
        """Attempt to acquire permission for an API call.

        Args:
            estimated_tokens: Expected total tokens (prompt + completion).

        Returns:
            bool: True if budget permits execution, False if rate limited.
        """
        now = time.monotonic()
        self._refill(self.rpm_bucket, now)
        self._refill(self.tpm_bucket, now)

        if self.rpm_bucket.tokens >= 1.0 and self.tpm_bucket.tokens >= estimated_tokens:
            self.rpm_bucket.tokens -= 1.0
            self.tpm_bucket.tokens -= estimated_tokens
            return True

        return False
