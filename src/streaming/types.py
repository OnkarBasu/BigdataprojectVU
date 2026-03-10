from __future__ import annotations

from typing import TypeAlias

RawRow: TypeAlias = tuple[str, str, str, str, str, str, str]
Chunk: TypeAlias = tuple[int, list[RawRow]]
