#!/usr/bin/env python3
"""Validate one ordinary Ikan JSON rule object without modifying it."""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List
from urllib.parse import urlparse


@dataclass(frozen=True)
class Issue:
    level: str
    field: str
    message: str


CONTENT_TYPES = {
    0,
    1,
    2,
    3,
    4,
    5,
    "manga",
    "漫画",
    "图片",
    "novel",
    "文字",
    "video",
    "视频",
    "audio",
    "音频",
    "rss",
    "mixed",
    "图文",
}

DEPRECATED_FIELDS = {
    "enableUpload",
    "searchItems",
    "discoverItems",
    "chapterItems",
}

ADDRESS_FIELDS = {
    "searchUrl",
    "searchNextUrl",
    "discoverUrl",
    "discoverNextUrl",
    "chapterUrl",
    "chapterNextUrl",
    "contentUrl",
    "contentNextUrl",
}

SELECTOR_FIELDS = {
    "searchNextUrl",
    "searchList",
    "searchTags",
    "searchName",
    "searchCover",
    "searchAuthor",
    "searchStatus",
    "searchChapter",
    "searchDescription",
    "searchResult",
    "discoverNextUrl",
    "discoverList",
    "discoverTags",
    "discoverName",
    "discoverCover",
    "discoverAuthor",
    "discoverStatus",
    "discoverChapter",
    "discoverDescription",
    "discoverResult",
    "chapterNextUrl",
    "chapterRoads",
    "chapterRoadName",
    "chapterList",
    "chapterName",
    "chapterCover",
    "chapterLock",
    "chapterTime",
    "chapterResult",
    "chapterPayload",
    "contentNextUrl",
    "contentItems",
}

CURRENT_NODE_VALUE_FIELDS = {
    "searchTags",
    "searchName",
    "searchCover",
    "searchAuthor",
    "searchStatus",
    "searchChapter",
    "searchDescription",
    "searchResult",
    "discoverTags",
    "discoverName",
    "discoverCover",
    "discoverAuthor",
    "discoverStatus",
    "discoverChapter",
    "discoverDescription",
    "discoverResult",
    "chapterRoadName",
    "chapterName",
    "chapterCover",
    "chapterLock",
    "chapterTime",
    "chapterResult",
    "chapterPayload",
}

CURRENT_NODE_COMPATIBILITY_READERS = {
    "@text",
    "@text()",
    "@html",
    "@outerHtml",
    "@href",
    "@src",
    "@data-src",
}

SUPPORTED_CSS_PSEUDO_CLASSES = {
    "root",
    "empty",
    "blank",
    "first-child",
    "last-child",
    "only-child",
    "first-of-type",
    "last-of-type",
    "only-of-type",
    "nth-child",
    "nth-last-child",
    "nth-of-type",
    "nth-last-of-type",
    "not",
    "link",
    "visited",
    "lang",
}

CSS_PSEUDO_CLASS_PATTERN = re.compile(r"(?<!:):([A-Za-z][A-Za-z-]*)")
CSS_PSEUDO_ELEMENT_PATTERN = re.compile(r"::([A-Za-z][A-Za-z-]*)")
WATERFALL_MARKER = "@@DiscoverRule:"
UNSUPPORTED_WATERFALL_SCRIPT_PATTERNS = (
    (re.compile(r"\b(?:const|let|var)\b"), "变量声明"),
    (re.compile(r"\.filter\s*\("), "filter()"),
    (re.compile(r"(?<!rules)\.map\s*\("), "map()"),
    (re.compile(r"\.push\s*\("), "push()"),
    (re.compile(r"\bencodeURIComponent\s*\("), "encodeURIComponent()"),
    (re.compile(r"\b(?!params\b)[A-Za-z_$][\w$]*\.join\s*\("), "自定义 join()"),
)
DIRECT_WATERFALL_FUNCTION_CALL_PATTERN = re.compile(
    r"^(?:return\s+)?(?!JSON\.stringify\b)([A-Za-z_$][\w$]*)\s*\(",
    re.DOTALL,
)


def _present(rule: dict, field: str) -> bool:
    value = rule.get(field)
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _error(field: str, message: str) -> Issue:
    return Issue("error", field, message)


def _warning(field: str, message: str) -> Issue:
    return Issue("warning", field, message)


def _require(rule: dict, fields: List[str], issues: List[Issue]) -> None:
    for field in fields:
        if not _present(rule, field):
            issues.append(_error(field, "字段已启用或属于主流程，但内容为空。"))


def _unsupported_css_pseudo_classes(value: str) -> List[str]:
    stripped = value.lstrip()
    lowered = stripped.lower()
    if lowered.startswith(("@js:", "@json:", "@xpath:")) or stripped.startswith(
        ("$", "//")
    ):
        return []
    if lowered.startswith("@css:"):
        stripped = stripped[5:]
    selector = stripped.split("@", 1)[0]
    pseudo_classes = {
        ":" + name
        for name in CSS_PSEUDO_CLASS_PATTERN.findall(selector)
        if name.lower() not in SUPPORTED_CSS_PSEUDO_CLASSES
    }
    pseudo_elements = {
        "::" + name for name in CSS_PSEUDO_ELEMENT_PATTERN.findall(selector)
    }
    return sorted(pseudo_classes | pseudo_elements)


def _unsupported_waterfall_script_features(value: str) -> List[str]:
    marker_index = value.find(WATERFALL_MARKER)
    if marker_index < 0:
        return []
    script = value[:marker_index].strip()
    if script.lower().startswith("@js:"):
        script = script[script.index(":") + 1 :].strip()
    unsupported = [
        label
        for pattern, label in UNSUPPORTED_WATERFALL_SCRIPT_PATTERNS
        if pattern.search(script)
    ]
    if DIRECT_WATERFALL_FUNCTION_CALL_PATTERN.search(script):
        unsupported.append("直接调用 loadJs/自定义函数")
    return unsupported


def _looks_like_eager_discover_request_object_list(value: str) -> bool:
    """Detect labeled request objects that ordinary discovery cannot use as categories."""
    stripped = value.lstrip()
    if not stripped.startswith("@js:") or WATERFALL_MARKER in value:
        return False
    return all(
        pattern.search(value)
        for pattern in (
            re.compile(r"\.map\s*\("),
            re.compile(r"\btitle\s*:"),
            re.compile(r"\burl\s*:"),
        )
    )


def validate_document(document: Any) -> List[Issue]:
    if not isinstance(document, dict):
        return [
            _error(
                "$",
                "需要一个普通 JSON 规则对象；不要传入数组、ikan:// 字符串或订阅文件。",
            )
        ]
    return validate_rule(document)


def validate_rule(rule: dict) -> List[Issue]:
    issues: List[Issue] = []

    _require(rule, ["id", "name", "host", "contentType"], issues)

    content_type = rule.get("contentType")
    if _present(rule, "contentType") and content_type not in CONTENT_TYPES:
        issues.append(
            _error(
                "contentType",
                "内容类型无效；使用 0-5 或字段字典支持的 manga/novel/video/audio/rss/mixed 别名。",
            )
        )

    chapter_source_order = rule.get("chapterSourceOrder")
    if _present(rule, "chapterSourceOrder") and chapter_source_order not in {
        "asc",
        "desc",
    }:
        issues.append(
            _error(
                "chapterSourceOrder",
                "chapterSourceOrder 只支持 asc 或 desc。",
            )
        )

    host = rule.get("host")
    if isinstance(host, str) and host.strip():
        parsed_host = urlparse(host)
        if parsed_host.scheme not in {"http", "https"} or not parsed_host.netloc:
            issues.append(_error("host", "host 必须是包含协议和域名的绝对 HTTP(S) 地址。"))

    if rule.get("enableSearch", True) is not False:
        _require(
            rule,
            ["searchUrl", "searchList", "searchName", "searchResult"],
            issues,
        )

    if rule.get("enableDiscover", True) is not False:
        _require(
            rule,
            ["discoverUrl", "discoverList", "discoverName", "discoverResult"],
            issues,
        )

    multi_roads_enabled = rule.get("enableMultiRoads") is True
    if multi_roads_enabled:
        _require(rule, ["chapterRoads", "chapterRoadName"], issues)
    else:
        for field in ("chapterRoads", "chapterRoadName"):
            if _present(rule, field):
                issues.append(
                    _warning(
                        field,
                        "enableMultiRoads 未开启，此多线路字段不会参与目录解析。",
                    )
                )

    _require(rule, ["chapterList", "chapterName", "contentItems"], issues)
    if not (_present(rule, "chapterResult") or _present(rule, "chapterPayload")):
        issues.append(
            _error(
                "chapterResult|chapterPayload",
                "目录阶段至少需要 chapterResult 或 chapterPayload。",
            )
        )

    ad_url = rule.get("adUrl")
    if isinstance(ad_url, str) and ad_url.strip():
        parsed_ad = urlparse(ad_url)
        if parsed_ad.scheme != "https" or not parsed_ad.netloc:
            issues.append(_error("adUrl", "广告数据地址必须是绝对 HTTPS 链接。"))
    elif ad_url is not None and not isinstance(ad_url, str):
        issues.append(_error("adUrl", "adUrl 必须是 HTTPS 字符串。"))

    for field in sorted(DEPRECATED_FIELDS.intersection(rule)):
        issues.append(_warning(field, "这是已废弃字段，新规则不应继续使用。"))

    for field in sorted(ADDRESS_FIELDS.intersection(rule)):
        value = rule.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        stripped = value.lstrip()
        is_js = stripped.startswith("@js:")
        if field == "discoverUrl":
            unsupported_waterfall = _unsupported_waterfall_script_features(value)
            if unsupported_waterfall:
                issues.append(
                    _error(
                        field,
                        "@@DiscoverRule: 使用受限模板求值器，不执行完整 JavaScript；"
                        "不支持：{}。请改用 ${{params.join(\"&\")}}、"
                        "${{values.xxx}}、${{page}} 或简单请求对象。".format(
                            ", ".join(unsupported_waterfall)
                        ),
                    )
                )
            if _looks_like_eager_discover_request_object_list(value):
                issues.append(
                    _warning(
                        field,
                        "普通 discoverUrl @js: 返回的 {title, url, headers} 对象列表"
                        "不能提供分类标题，并会在分类初始化时提前固定 page/签名。"
                        "请让外层 JS 返回“分类::名称::@js:请求表达式”，"
                        "由内层 @js: 在实际页码请求时调用 apiRequest()。",
                    )
                )
        if not is_js and stripped[:1] in {"{", "["}:
            issues.append(
                _error(
                    field,
                    "结构化或动态请求必须以 @js: 开头并返回请求对象，不能把 JSON 对象序列化成普通地址字符串。",
                )
            )
        if is_js and ("$keyword" in value or "$page" in value):
            issues.append(
                _warning(
                    field,
                    "@js: 中直接使用 keyword/page，不要写成 $keyword/$page。",
                )
            )
        if not is_js and ("${keyword}" in value or "${page}" in value):
            issues.append(
                _warning(
                    field,
                    "普通地址模板使用 $keyword/$page；${...} 只应出现在 @js: JavaScript 模板字符串中。",
                )
            )

    for field in sorted(SELECTOR_FIELDS.intersection(rule)):
        value = rule.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        unsupported = _unsupported_css_pseudo_classes(value)
        if unsupported:
            issues.append(
                _error(
                    field,
                    "CSS 伪类暂不支持：{}。请改用受支持的结构伪类或 JavaScript。".format(
                        ", ".join(unsupported)
                    ),
                )
            )

    for field in sorted(CURRENT_NODE_VALUE_FIELDS.intersection(rule)):
        value = rule.get(field)
        if not isinstance(value, str):
            continue
        if value.strip() in CURRENT_NODE_COMPATIBILITY_READERS:
            issues.append(
                _warning(
                    field,
                    "当前列表节点本身取值时使用 text/href 等规范写法，不加前导 @；当前写法仅作兼容。",
                )
            )

    return issues


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rule", type=Path, help="包含一个普通 JSON 规则对象的文件")
    args = parser.parse_args(argv)

    try:
        document = _load(args.rule)
    except (OSError, json.JSONDecodeError) as exc:
        print("ERROR $: 无法读取有效 JSON：{}".format(exc))
        return 1

    issues = validate_document(document)
    for issue in issues:
        print("{} {}: {}".format(issue.level.upper(), issue.field, issue.message))

    errors = sum(issue.level == "error" for issue in issues)
    warnings = sum(issue.level == "warning" for issue in issues)
    if errors:
        print("FAILED: {} error(s), {} warning(s)".format(errors, warnings))
        return 1

    print("OK: 0 error(s), {} warning(s)".format(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
