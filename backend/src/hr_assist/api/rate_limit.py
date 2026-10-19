import logging
import math
from collections import deque
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from hr_assist.settings import Settings

Clock = Callable[[], datetime]
MINUTE = timedelta(minutes=1)

logger = logging.getLogger("hr_assist.rate_limit")


def utc_now() -> datetime:
    return datetime.now(UTC)


class RateLimited(Exception):
    def __init__(self, limit: str, message: str, retry_after: timedelta) -> None:
        super().__init__(message)
        self.limit = limit
        self.retry_after_seconds = max(1, math.ceil(retry_after.total_seconds()))


class RateLimiter:
    """Counts chats per client IP and in total, in memory (one instance only, ADR 0003)."""

    def __init__(self, settings: Settings, clock: Clock) -> None:
        self.settings = settings
        self.clock = clock
        self._recent: dict[str, deque[datetime]] = {}
        self._day: date | None = None
        self._per_ip_today: dict[str, int] = {}
        self._total_today = 0

    def admit(self, client_ip: str) -> None:
        """Counts one chat from client_ip, or raises RateLimited without counting it."""
        now = self.clock().astimezone(UTC)
        if now.date() != self._day:
            self._day = now.date()
            self._per_ip_today = {}
            self._total_today = 0
            self._recent = {
                ip: recent for ip, recent in self._recent.items() if recent[-1] > now - MINUTE
            }
        until_tomorrow = datetime.combine(now.date() + timedelta(days=1), time(), UTC) - now

        recent = self._recent.pop(client_ip, deque())
        while recent and recent[0] <= now - MINUTE:
            recent.popleft()
        if recent:
            # Only non-empty windows are stored, so the rollover above can read recent[-1].
            self._recent[client_ip] = recent

        if len(recent) >= self.settings.rate_limit_per_minute:
            self._reject(
                "per_ip_minute",
                "You're asking questions too quickly. Please wait a minute and try again.",
                recent[0] + MINUTE - now,
                client_ip,
            )

        if self._per_ip_today.get(client_ip, 0) >= self.settings.rate_limit_per_day:
            self._reject(
                "per_ip_day",
                "You've reached today's limit of questions. Please come back tomorrow.",
                until_tomorrow,
                client_ip,
            )

        if self._total_today >= self.settings.rate_limit_global_per_day:
            self._reject(
                "global_day",
                "HR Assist has answered as many questions as it can today. "
                "Please come back tomorrow.",
                until_tomorrow,
                client_ip,
            )

        recent.append(now)
        self._recent[client_ip] = recent
        self._per_ip_today[client_ip] = self._per_ip_today.get(client_ip, 0) + 1
        self._total_today += 1

    def _reject(self, limit: str, message: str, retry_after: timedelta, client_ip: str) -> None:
        error = RateLimited(limit, message, retry_after)
        logger.warning(
            "Rate limited: %s limit hit by %s, retry after %ss",
            limit,
            client_ip,
            error.retry_after_seconds,
        )
        raise error
