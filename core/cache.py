# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Simple in-memory LRU cache for analysis results."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


class AnalysisCache:
    """LRU cache that stores recent analysis results keyed by file+settings."""

    def __init__(self, max_size: int = 10) -> None:
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size

    @staticmethod
    def _make_key(file_path: str, settings: dict) -> str:
        settings_hash = hash(frozenset(settings.items()))
        return f"{file_path}_{settings_hash}"

    def get(self, file_path: str, settings: dict) -> Any | None:
        """Return cached result or None if not found."""
        key = self._make_key(file_path, settings)
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def put(self, file_path: str, settings: dict, result: Any) -> None:
        """Store a result, evicting the oldest entry if at capacity."""
        key = self._make_key(file_path, settings)
        if key in self._store:
            self._store.move_to_end(key)
        else:
            if len(self._store) >= self._max_size:
                self._store.popitem(last=False)
        self._store[key] = result

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()


# Module-level singleton instance used by the addon.
analysis_cache = AnalysisCache()
