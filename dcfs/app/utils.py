import posixpath
from typing import Tuple

from dcfs.errors import TechnicalError


def normalize_global_path(path: str) -> str:
    if not path:
        return "/"

    path = path.replace("\\", "/")
    if not path.startswith("/"):
        path = f"/{path}"

    parts = [p for p in path.split("/") if p]
    if any(p == ".." for p in parts):
        raise TechnicalError(f"Parent path segments are not allowed. Got: {path}")

    normalized = posixpath.normpath(path)
    if normalized in ("", "."):
        return "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def split_global_path(path: str) -> Tuple[str, str]:
    """
    Split a path into the client name and the sub path.
    Example:
        - Input: "notes-1/test/test.txt"
        - Output: ("notes-1", "test/test.txt")
    """
    path = normalize_global_path(path)
    parts = path.split("/", 2)
    if len(parts) < 1:
        raise TechnicalError(f"Path must begin with a client name. Got: {path}")
    if len(parts) == 2:
        return parts[1], ""
    return parts[1], parts[2]
