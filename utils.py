"""Small shared helpers used across the reel pipeline."""

import logging
import time
from typing import Callable, Optional, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    exceptions: Sequence[type] = (Exception,),
    description: str = "operation",
) -> T:
    """
    Call ``func`` and retry it with exponential backoff if it raises.

    Re-raises the last exception once all attempts are exhausted, so failures
    surface instead of being silently swallowed.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except exceptions as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt >= attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                description, attempt, attempts, exc, delay,
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


_LONG_DASHES = ("\u2014", "\u2013", "\u2012", "\u2015")  # em, en, figure, horizontal bar


def clean_text(text):
    """
    Replace long dashes with a spaced hyphen and non-breaking hyphens with '-'.

    Returns the text with runs of whitespace collapsed. Non-string input is
    returned unchanged.
    """
    if not isinstance(text, str):
        return text
    for dash in _LONG_DASHES:
        text = text.replace(dash, " - ")
    text = text.replace("\u2011", "-")  # non-breaking hyphen
    return " ".join(text.split())
