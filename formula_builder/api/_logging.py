"""Structured logging & circuit breaker for Formula Builder (Phase 3.2).

Usage:
  from formula_builder.api._logging import get_logger, CircuitBreaker, timed

  logger = get_logger()
  logger.info("engine_compile", formula_hash=hash, compile_ms=elapsed)

  cache_cb = CircuitBreaker("redis_cache", failure_threshold=5, recovery_timeout=30)
  if cache_cb.allow():
      try:
          value = frappe.cache().get_value(key)
          cache_cb.success()
      except Exception:
          cache_cb.failure()
          value = fallback_read_db()

  @timed("evaluate_formula")
  def evaluate_formula(...): ...
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import frappe

# ============================================================================
# CORRELATION LOGGER
# ============================================================================


class FormulaLogger:
    """Logger có cấu trúc với correlation_id cho mỗi request."""

    def __init__(self):
        self._module = "formula_builder"

    def _emit(self, level: str, event: str, **kwargs):
        """Emit log entry với correlation_id nếu có."""
        try:
            corr_id = getattr(frappe.local, "fb_correlation_id", None) or "-"
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "event": event,
                "module": self._module,
                "correlation_id": corr_id,
                **kwargs,
            }
            frappe.log_error(
                json.dumps(payload, ensure_ascii=False, default=str),
                f"FB:{event}",
            )
        except Exception:
            pass

    def info(self, event: str, **kwargs):
        self._emit("INFO", event, **kwargs)

    def warn(self, event: str, **kwargs):
        self._emit("WARN", event, **kwargs)

    def error(self, event: str, **kwargs):
        self._emit("ERROR", event, **kwargs)

    def metric(self, name: str, value: float, **tags):
        """Ghi metric (latency, count, etc.) — dùng cho monitoring."""
        self._emit("METRIC", name, value=value, **tags)


# Singleton
_logger_instance: Optional[FormulaLogger] = None


def get_logger() -> FormulaLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = FormulaLogger()
    return _logger_instance


def set_correlation_id():
    """Generate correlation_id cho request hiện tại — gọi trong before_request hook."""
    frappe.local.fb_correlation_id = str(uuid.uuid4())[:8]


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================


class CircuitBreaker:
    """Circuit breaker pattern — ngăn cascading failure khi Redis/dependency down.

    States: CLOSED → OPEN (sau N lần fail) → HALF_OPEN (sau recovery_timeout)

    Usage:
        cache_cb = CircuitBreaker("redis_cache")
        if cache_cb.allow():
            try:
                value = frappe.cache().get_value(key)
                cache_cb.success()
            except Exception:
                cache_cb.failure()
                value = fallback()
        else:
            value = fallback()  # circuit open → skip cache
    """

    CLOSED = "closed"       # Normal — requests pass through
    OPEN = "open"           # Failing — requests blocked, fast-fail
    HALF_OPEN = "half_open" # Testing — single probe request

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self._cache_key = f"fb_cb:{name}"

    def _get_state(self) -> dict:
        try:
            raw = frappe.cache().get_value(self._cache_key)
            if raw:
                return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            pass
        return {"state": self.CLOSED, "failures": 0, "last_failure": 0}

    def _set_state(self, state: dict):
        try:
            frappe.cache().set_value(
                self._cache_key,
                json.dumps(state),
                expires_in_sec=self.recovery_timeout * 2,
            )
        except Exception:
            pass

    def allow(self) -> bool:
        """Return True nếu request được phép đi qua."""
        s = self._get_state()
        now = time.monotonic()

        if s["state"] == self.CLOSED:
            return True

        if s["state"] == self.OPEN:
            if now - s["last_failure"] >= self.recovery_timeout:
                # Transition to HALF_OPEN
                s["state"] = self.HALF_OPEN
                self._set_state(s)
                return True
            return False

        # HALF_OPEN — allow probe
        return True

    def success(self):
        """Báo thành công — reset về CLOSED."""
        self._set_state({"state": self.CLOSED, "failures": 0, "last_failure": 0})

    def failure(self):
        """Báo thất bại — increment counter, có thể mở circuit."""
        s = self._get_state()
        s["failures"] += 1
        s["last_failure"] = time.monotonic()

        if s["failures"] >= self.failure_threshold:
            s["state"] = self.OPEN
            get_logger().warn(
                "circuit_breaker_open",
                name=self.name,
                failures=s["failures"],
            )

        self._set_state(s)


# ============================================================================
# TIMING DECORATOR
# ============================================================================


def timed(action: str):
    """Decorator đo thời gian thực thi và ghi metric.

    Usage:
        @timed("evaluate_formula")
        def evaluate_formula(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            t0 = time.monotonic()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.monotonic() - t0) * 1000
                get_logger().metric(
                    f"{action}.success",
                    elapsed_ms,
                    action=action,
                )
                return result
            except Exception as e:
                elapsed_ms = (time.monotonic() - t0) * 1000
                get_logger().metric(
                    f"{action}.error",
                    elapsed_ms,
                    action=action,
                    error_type=type(e).__name__,
                )
                raise
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
