"""Reading optional settings from environment variables, with defaults set in code."""

import math
import os
from decimal import Decimal, InvalidOperation


def _raw(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip()


def int_env(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a whole number") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"{name} must be at most {maximum}")
    return value


def float_env(name: str, default: float, minimum: float) -> float:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not math.isfinite(value) or value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def decimal_env(name: str, default: Decimal, minimum: Decimal) -> Decimal:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not value.is_finite() or value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value
