# mypy: ignore-errors
from typing import Dict

from dcfs.core.cache import FSCache

__all__ = [
    "FSCache",
    "gfc",
]

gfc: Dict[str, FSCache] = {}
