from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def _normalize(value: str) -> str:
    value = value.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def _translate(pattern: str) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                while index + 1 < len(pattern) and pattern[index + 1] == "*":
                    index += 1
                pieces.append(".*")
            else:
                pieces.append("[^/]*")
        elif char == "?":
            pieces.append("[^/]")
        elif char == "[":
            end = index + 1
            if end < len(pattern) and pattern[end] in "!^":
                end += 1
            if end < len(pattern) and pattern[end] == "]":
                end += 1
            while end < len(pattern) and pattern[end] != "]":
                end += 1
            if end == len(pattern):
                pieces.append(r"\[")
            else:
                content = pattern[index + 1 : end]
                if content.startswith("!"):
                    content = "^/" + content[1:]
                elif content.startswith("^"):
                    content = "\\" + content
                content = content.replace("\\", r"\\")
                pieces.append("[" + content + "]")
                index = end
        else:
            pieces.append(re.escape(char))
        index += 1
    return "".join(pieces)


def matches(pattern: str, path: str) -> bool:
    """Match one normalized repository path against an affects glob."""
    normalized_pattern = _normalize(pattern)
    normalized_path = _normalize(path)
    if os.name == "nt":
        normalized_pattern = normalized_pattern.lower()
        normalized_path = normalized_path.lower()
    prefix = r"(?:.*/)?" if "/" not in normalized_pattern else ""
    return re.fullmatch(prefix + _translate(normalized_pattern), normalized_path) is not None


def matches_affects(affects: Iterable[Mapping[str, Any]], path: str) -> bool:
    """Apply positive and negative path affects entries to a repository path."""
    path_entries = [item for item in affects if item.get("type") == "path"]
    positive = any(
        not item.get("negate", False)
        and isinstance(item.get("pattern"), str)
        and matches(item["pattern"], path)
        for item in path_entries
    )
    excluded = any(
        item.get("negate", False)
        and isinstance(item.get("pattern"), str)
        and matches(item["pattern"], path)
        for item in path_entries
    )
    return positive and not excluded


def to_repo_relative(root: str | Path, path: str | Path) -> str | None:
    """Return a normalized repository-relative path, or None when outside."""
    root_text = os.path.realpath(os.fspath(root))
    path_text = os.fspath(path).replace("\\", os.sep)
    if not os.path.isabs(path_text):
        path_text = os.path.join(root_text, path_text)
    path_text = os.path.realpath(path_text)
    if os.name == "nt":
        root_text = root_text.lower()
        path_text = path_text.lower()
    try:
        relative = os.path.relpath(path_text, root_text)
    except ValueError:
        # Windows raises for paths on different drives. Such a target is outside.
        return None
    relative = relative.replace("\\", "/")
    if relative == ".." or relative.startswith("../"):
        return None
    relative = _normalize(relative)
    return relative.lower() if os.name == "nt" else relative
