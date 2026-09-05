"""Tolerant, non-executing input reader for Legado source batches."""

import json
from pathlib import Path
from typing import Any, List, Tuple

from .models import Diagnostic, ParsedSource, SourceLocation


def _diagnostic(origin: str, message: str, excerpt: str = "") -> Diagnostic:
    return Diagnostic(
        code="input.invalid_json",
        severity="error",
        field=origin,
        message=message,
        excerpt=excerpt[:240],
    )


def parse_text(
    text: str, origin: str
) -> Tuple[List[ParsedSource], List[Diagnostic]]:
    decoder = json.JSONDecoder()
    source = text.lstrip("\ufeff")
    cursor = 0
    values: List[Any] = []
    diagnostics: List[Diagnostic] = []

    while True:
        while cursor < len(source) and (source[cursor].isspace() or source[cursor] == ","):
            cursor += 1
        if cursor >= len(source):
            break
        try:
            value, end = decoder.raw_decode(source, cursor)
        except json.JSONDecodeError as error:
            diagnostics.append(
                _diagnostic(
                    origin,
                    "无法从第 {} 个字符解析 JSON：{}".format(error.pos, error.msg),
                    source[cursor : cursor + 240],
                )
            )
            break
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
        cursor = end

    parsed: List[ParsedSource] = []
    for index, value in enumerate(values, start=1):
        location = SourceLocation(origin=origin, index=index)
        if not isinstance(value, dict):
            diagnostics.append(
                Diagnostic(
                    code="input.not_object",
                    severity="warning",
                    field=location.label,
                    message="Legado 条目必须是 JSON 对象，已跳过。",
                    excerpt=str(value)[:240],
                )
            )
            continue
        parsed.append(ParsedSource(value=value, location=location))
    return parsed, diagnostics


def load_inputs(path: Path) -> Tuple[List[ParsedSource], List[Diagnostic]]:
    if path.is_dir():
        candidates = sorted(
            (
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in {".json", ".txt"}
            ),
            key=lambda item: item.as_posix(),
        )
    elif path.is_file():
        candidates = [path]
    else:
        return [], [_diagnostic(str(path), "输入路径不存在或不是普通文件/目录。")]

    parsed: List[ParsedSource] = []
    diagnostics: List[Diagnostic] = []
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            diagnostics.append(_diagnostic(str(candidate), "无法读取输入：{}".format(error)))
            continue
        items, issues = parse_text(text, str(candidate))
        parsed.extend(items)
        diagnostics.extend(issues)
    return parsed, diagnostics
