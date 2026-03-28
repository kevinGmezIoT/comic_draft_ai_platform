import contextvars
import os
from contextlib import contextmanager
from functools import wraps
from time import perf_counter


def _env_enabled(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default)
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


@contextmanager
def timed_step(label: str):
    if not _env_enabled("COMIC_AGENT_TIMING", "1"):
        yield
        return

    start = perf_counter()
    try:
        yield
    finally:
        elapsed = perf_counter() - start
        print(f"TIMING: {label} took {elapsed:.3f}s")


def timed_function(label: str | None = None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            step_label = label or func.__qualname__
            with timed_step(step_label):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def submit_with_current_context(executor, fn, *args, **kwargs):
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)
