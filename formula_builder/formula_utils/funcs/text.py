# formula_utils/funcs/text.py
# Text manipulation functions for formula engine

from typing import Any

# Import safe_str from normalize to avoid duplication
from ..normalize import safe_str


def concat(*args) -> str:
    """Concatenate arguments, skipping None."""
    return ''.join(str(x) for x in args if x is not None)


def concatenate(*args) -> str:
    """Alias for concat."""
    return "".join(safe_str(x) for x in args)


def text_join(delimiter, *args) -> str:
    """Join arguments with delimiter, skipping None."""
    return str(delimiter).join(str(x) for x in args if x is not None)


def textjoin(delimiter: str = ', ', ignore_empty: bool = True, *texts) -> str:
    """
    Join texts with delimiter, optionally ignoring empty values.
    Parameters:
        delimiter: separator string
        ignore_empty: if True, skip empty strings/None
        *texts: variable number of text arguments
    """
    parts = []
    for t in texts:
        s = safe_str(t)
        if not ignore_empty or s:
            parts.append(s)
    return delimiter.join(parts)


def left(text: Any, n: int = 1) -> str:
    """Return first n characters of text."""
    return str(text)[:int(n)]


def right(text: Any, n: int = 1) -> str:
    """Return last n characters of text."""
    return str(text)[-int(n):]


def mid(text: Any, start: int, length: int) -> str:
    """
    Return substring from start (1-indexed) of given length.
    Parameters:
        start: starting position (1-indexed)
        length: number of characters to extract
    """
    s = str(text)
    start_idx = int(start) - 1
    end_idx = start_idx + int(length)
    return s[start_idx:end_idx]


def upper(text: Any) -> str:
    """Convert text to uppercase."""
    return str(text).upper()


def lower(text: Any) -> str:
    """Convert text to lowercase."""
    return str(text).lower()


def trim(text: Any) -> str:
    """Strip leading/trailing whitespace."""
    return str(text).strip()


def replace(text: Any, old: Any, new: Any) -> str:
    """Replace all occurrences of old with new in text."""
    return str(text).replace(str(old), str(new))


def substitute(text: Any, old: Any, new: Any, nth: int = None) -> str:
    """
    Replace old with new in text.
    If nth is specified, replace only the nth occurrence.
    """
    text_str = str(text)
    old_str = str(old)
    new_str = str(new)

    if nth is None:
        return text_str.replace(old_str, new_str)

    parts = text_str.split(old_str)
    if nth < 1 or nth > len(parts) - 1:
        return text_str
    return old_str.join(parts[:nth]) + new_str + old_str.join(parts[nth:])


def find_text(search: Any, text: Any, start: int = 1) -> int:
    """
    Find position of search string in text (1-indexed).
    Returns 0 if not found.
    """
    try:
        return str(text).index(str(search), int(start) - 1) + 1
    except ValueError:
        return 0


# Alias for find_text
find = find_text


def len_text(text: Any) -> int:
    """Return length of text string."""
    return len(str(text))