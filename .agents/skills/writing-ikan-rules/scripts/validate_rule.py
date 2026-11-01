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



def _https_origin(value, root=False):
    if not isinstance(value, str):
        return None
    try:
        url = urlparse(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            return None
        if root and (url.path not in ("", "/") or url.query or url.fragment):
            return None
        port = url.port
        return "https://" + url.hostname.lower() + (":" + str(port) if port and port != 443 else "")
    except ValueError:
        return None


def _validate_auth(rule, issues):
    if rule.get("loginUrl"):
        issues.append(_warning("loginUrl", "旧字段仅供导入兼容；新规则请使用 auth.entries 的 webview 入口。"))
    if rule.get("cookies"):
        issues.append(_error("cookies", "实际 Cookie 不得写入分享规则，请通过客户端登录管理保存。"))
    user_agent = rule.get("userAgent")
    if isinstance(user_agent, str) and user_agent.lstrip().startswith("{"):
        try:
            headers = json.loads(user_agent)
        except (ValueError, TypeError):
            headers = {}
        if isinstance(headers, dict) and any(str(k).lower() in {"cookie", "authorization", "proxy-authorization", "x-auth-token", "x-access-token"} and v for k, v in headers.items()):
            issues.append(_error("userAgent", "全局请求头含实际认证凭据；请改用 auth.inject 模板或网页登录会话。"))
    auth = rule.get("auth")
    if auth is None or auth == {}:
        return
    if not isinstance(auth, dict):
        issues.append(_error("auth", "auth 必须是 JSON 对象。"))
        return
    if type(auth.get("version")) is not int or auth["version"] != 1:
        issues.append(_error("auth.version", "当前仅支持整数版本 1。"))
    if "allowHostSwitch" in auth and type(auth["allowHostSwitch"]) is not bool:
        issues.append(_error("auth.allowHostSwitch", "必须为布尔值；仅在确认镜像共享认证并声明 origins 后启用。"))
    required = auth.get("requiredFor", [])
    allowed = {"all", "discover", "search", "detail", "chapter", "content"}
    if not isinstance(required, list) or any(not isinstance(op, str) or op not in allowed for op in required):
        issues.append(_error("auth.requiredFor", "使用操作数组：all、discover、search、detail、chapter、content。chapterLock 不参与此声明。"))
    entries = auth.get("entries", [])
    if not isinstance(entries, list):
        issues.append(_error("auth.entries", "entries 必须是登录入口数组。"))
        entries = []
    if required and not entries and not rule.get("loginUrl"):
        issues.append(_error("auth.entries", "声明了登录要求但没有登录入口。"))
    for index, entry in enumerate(entries):
        field = "auth.entries[{}]".format(index)
        if not isinstance(entry, dict):
            issues.append(_error(field, "入口必须是 JSON 对象。"))
            continue
        if not isinstance(entry.get("type"), str) or entry["type"] not in {"api", "manual", "webview"}:
            issues.append(_error(field + ".type", "入口类型仅支持 api、manual、webview。"))
        fields = entry.get("fields", [])
        if not isinstance(fields, list):
            issues.append(_error(field + ".fields", "登录表单 fields 必须是数组。"))
            fields = []
        for field_index, form_field in enumerate(fields):
            if isinstance(form_field, dict) and "defaultValue" in form_field:
                if entry.get("type") != "api" or not isinstance(form_field["defaultValue"], str):
                    issues.append(_error(field + ".fields[{}].defaultValue".format(field_index), "defaultValue 仅用于 API 表单的字符串公开初始值，不用于网页登录或手动凭据。"))
        if entry.get("type") == "webview":
            origins = entry.get("origins", [])
            origin_set = {_https_origin(v, root=True) for v in origins} if isinstance(origins, list) else {None}
            if not origins or None in origin_set or _https_origin(entry.get("url")) not in origin_set:
                issues.append(_error(field, "网页登录 url 必须属于明确允许的 HTTPS origins。"))
        if "cookieMode" in entry:
            if entry.get("type") != "webview" or entry["cookieMode"] != "all" or entry.get("extract"):
                issues.append(_error(field + ".cookieMode", "cookieMode: all 仅用于网页登录，不能同时配置 extract。"))
    for key in ("prepare", "inject"):
        if key in auth and (not isinstance(auth[key], list) or any(not isinstance(v, dict) for v in auth[key])):
            issues.append(_error("auth." + key, "必须是 JSON 对象数组。"))
    if isinstance(auth.get("inject"), list):
        for index, injection in enumerate(auth["inject"]):
            if not isinstance(injection, dict):
                continue
            origins = injection.get("origins", [])
            field = "auth.inject[{}]".format(index)
            if not isinstance(origins, list) or not origins or any(_https_origin(v, root=True) is None for v in origins):
                issues.append(_error(field + ".origins", "凭据只能注入明确允许的 HTTPS 来源。"))
            template = injection.get("template")
            if not isinstance(template, str) or not re.search(r"\{\{[A-Za-z0-9_]+\}\}", template):
                issues.append(_error(field + ".template", "使用 {{凭据名}} 引用，不要写入实际 Token/Cookie。"))
    for key in ("check", "expired", "refresh", "logout"):
        if key in auth and not isinstance(auth[key], dict):
            issues.append(_error("auth." + key, "必须是 JSON 对象。"))
    registration = auth.get("registration")
    if registration is not None:
        origins = registration.get("origins", []) if isinstance(registration, dict) else []
        origin_set = {_https_origin(v, root=True) for v in origins} if isinstance(origins, list) else {None}
        if not isinstance(registration, dict) or not origins or None in origin_set or _https_origin(registration.get("url")) not in origin_set:
            issues.append(_error("auth.registration", "注册 url 必须属于明确允许的 HTTPS origins；不要猜测注册链接。"))


def _validate_backup_hosts(rule, issues):
    values = rule.get("backupHosts")
    if values is None:
        return
    if not isinstance(values, list):
        issues.append(_error("backupHosts", "backupHosts 必须是来源数组。"))
        return
    primary = urlparse(rule.get("host", "")) if isinstance(rule.get("host"), str) else None
    if values and (primary is None or primary.scheme not in {"http", "https"} or not primary.hostname or primary.username or primary.password):
        issues.append(_error("host", "配置备用域名前需要有效的主域名。"))
    unique = set()
    for value in values:
        try:
            url = urlparse(value) if isinstance(value, str) else None
            if url is None or url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment or (primary and primary.scheme == "https" and url.scheme != "https"):
                raise ValueError()
            origin = (url.scheme, url.hostname.lower(), url.port or (443 if url.scheme == "https" else 80))
            primary_origin = (primary.scheme, primary.hostname.lower(), primary.port or (443 if primary.scheme == "https" else 80)) if primary and primary.hostname else None
            if origin != primary_origin:
                unique.add(origin)
        except (ValueError, TypeError):
            issues.append(_error("backupHosts", "备用域名必须是完整 HTTP(S) 来源，不含路径、参数、账号或片段；HTTPS 主站不能降级。"))
    if len(unique) > 8:
        issues.append(_error("backupHosts", "最多配置 8 个备用域名。"))

def validate_rule(rule: dict) -> List[Issue]:
    issues: List[Issue] = []
    _validate_auth(rule, issues)
    _validate_backup_hosts(rule, issues)

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
