from __future__ import annotations

from typing import TypeAlias

from src.models import AISRecord

Chunk: TypeAlias = tuple[int, list[AISRecord]]
