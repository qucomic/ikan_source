"""Conservative, offline Legado-to-Ikan rule conversion."""

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .capability_scanner import redact_excerpt, scan_capabilities
from .models import ConversionResult, Diagnostic, ParsedSource


_CONTENT_TYPES = {0: "novel", 1: "audio", 2: "manga", 3: "mixed"}
_ABSOLUTE_URL = re.compile(r"https?://[^\s\"'<>\\,]+", re.IGNORECASE)
_TEMPLATE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_PAGE_ARITHMETIC = re.compile(r"^[\d\s()+\-*/%]*\bpage\b[\d\s()+\-*/%]*$")


def _identity(source: Mapping[str, Any]) -> str:
    name = str(source.get("bookSourceName", "")).strip()
    url = str(source.get("bookSourceUrl", "")).strip()
    return name + "\n" + url


def _digest(identity: str, length: int) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:length]


def safe_output_name(name: str, identity: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip()
    stem = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", normalized, flags=re.UNICODE)
    stem = re.sub(r"-+", "-", stem).strip("-_")[:64] or "legado-rule"
    return "{}-{}.json".format(stem, _digest(identity, 8))


def _issue(
    diagnostics: List[Diagnostic],
    code: str,
    field: str,
    message: str,
    value: Any = "",
    severity: str = "warning",
) -> None:
    diagnostics.append(
        Diagnostic(
            code=code,
            severity=severity,
            field=field,
            message=message,
            excerpt=redact_excerpt(value) if value not in (None, "") else "",
        )
    )


def _walk_strings(value: Any):
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, str):
        yield value


def _host_from_url(value: str) -> Optional[str]:
    match = _ABSOLUTE_URL.search(value)
    if not match:
        return None
    parsed = urlparse(match.group(0).split("#", 1)[0])
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return "{}://{}".format(parsed.scheme.lower(), parsed.netloc)


def _derive_host(source: Mapping[str, Any]) -> str:
    source_url = source.get("bookSourceUrl")
    if isinstance(source_url, str):
        host = _host_from_url(source_url)
        if host:
            return host
    for value in _walk_strings(source):
        host = _host_from_url(value)
        if host:
            return host
    return ""


def _template_replacement(expression: str, *, js_body: bool) -> Optional[str]:
    normalized = expression.strip()
    if normalized in {"key", "keyword"}:
        return "${encodeURIComponent(keyword)}" if js_body else "$keyword"
    if normalized == "page":
        return "${page}" if js_body else "$page"
    if normalized in {"result", "lastResult"}:
        return "${result}" if js_body else "$result"
    if normalized == "baseUrl":
        return "${baseUrl}" if js_body else "$baseUrl"
    if normalized == "host":
        return "${host}" if js_body else "$host"
    if _PAGE_ARITHMETIC.fullmatch(normalized):
        return "${" + normalized + "}"
    return None


def _convert_template(
    value: str,
    field: str,
    diagnostics: List[Diagnostic],
    *,
    js_body: bool = False,
) -> Optional[str]:
    unsupported: List[str] = []

    def replace(match: re.Match) -> str:
        replacement = _template_replacement(match.group(1), js_body=js_body)
        if replacement is None:
            unsupported.append(match.group(1).strip())
            return match.group(0)
        return replacement

    converted = _TEMPLATE.sub(replace, value)
    if unsupported:
        _issue(
            diagnostics,
            "conversion.template_unsupported",
            field,
            "包含无法离线转换的 Legado 模板表达式：{}。".format(
                ", ".join(unsupported[:3])
            ),
            value,
        )
        return None
    return converted


def _split_request_config(value: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    decoder = json.JSONDecoder()
    for match in re.finditer(r",\s*\{", value):
        object_start = value.find("{", match.start())
        try:
            config, end = decoder.raw_decode(value, object_start)
        except json.JSONDecodeError:
            continue
        if isinstance(config, dict) and not value[end:].strip():
            return value[: match.start()].strip(), config
    return None


def _js_string_template(
    value: str, field: str, diagnostics: List[Diagnostic]
) -> Optional[str]:
    escaped = value.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    return _convert_template(escaped, field, diagnostics, js_body=True)


def _convert_address(
    value: Any, field: str, diagnostics: List[Diagnostic]
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    source = value.strip()
    if source.lower().startswith(("@js:", "<js>")):
        _issue(
            diagnostics,
            "conversion.script_unsupported",
            field,
            "地址脚本需要专门的运行时重写。",
            source,
        )
        return None
    request = _split_request_config(source)
    if request is None:
        return _convert_template(source, field, diagnostics)

    url, config = request
    converted_url = _convert_template(url, field, diagnostics)
    if converted_url is None:
        return None
    method = str(config.get("method", "GET")).upper()
    properties = ["url:" + json.dumps(converted_url, ensure_ascii=False)]
    properties.append("method:" + json.dumps(method))
    headers = config.get("headers")
    if isinstance(headers, Mapping):
        properties.append(
            "headers:" + json.dumps(headers, ensure_ascii=False, separators=(",", ":"))
        )
    body = config.get("body")
    if isinstance(body, str):
        converted_body = _js_string_template(body, field, diagnostics)
        if converted_body is None:
            return None
        properties.append("body:`" + converted_body + "`")
    elif body is not None:
        properties.append(
            "body:" + json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        )
    if config.get("charset"):
        properties.append("requestEncoding:" + json.dumps(str(config["charset"])))
    return "@js:({" + ",".join(properties) + "})"


def _convert_css_shorthand(value: str) -> str:
    reader = ""
    base = value
    if "@" in value:
        base, suffix = value.rsplit("@", 1)
        if suffix in {"text", "href", "src", "html", "outerHtml", "data-src"}:
            reader = "@" + suffix
        elif re.fullmatch(r"[A-Za-z][\w-]*", suffix):
            reader = " " + suffix
        else:
            return value
    match = re.fullmatch(r"(class|tag|id)\.([\w-]+)(?:\.(\d+))?", base)
    if not match:
        return value
    kind, name, index = match.groups()
    if kind == "class":
        selector = "." + name
    elif kind == "id":
        selector = "#" + name
    else:
        selector = name
    if index is not None:
        selector += ":nth-of-type({})".format(int(index) + 1)
    return selector + reader


def _convert_selector(
    value: Any, field: str, diagnostics: List[Diagnostic]
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    source = value.strip()
    if source.startswith("<XPath>"):
        return "@xpath:" + source[len("<XPath>") :].strip()
    if source.lower().startswith(("<js>", "@js:")):
        _issue(
            diagnostics,
            "conversion.selector_unsupported",
            field,
            "选择器脚本需要专门转换。",
            source,
        )
        return None
    if "{{" in source:
        _issue(
            diagnostics,
            "conversion.selector_unsupported",
            field,
            "复合模板选择器无法可靠离线转换。",
            source,
        )
        return None
    branches = re.split(r"(&&|\|\|)", source)
    return "".join(
        part if part in {"&&", "||"} else _convert_css_shorthand(part.strip())
        for part in branches
    )


def _copy_metadata(source: Mapping[str, Any], diagnostics: List[Diagnostic]) -> Dict[str, Any]:
    identity = _identity(source)
    source_type = source.get("bookSourceType", 0)
    content_type = _CONTENT_TYPES.get(source_type)
    if content_type is None:
        content_type = "mixed"
        _issue(
            diagnostics,
            "conversion.content_type",
            "$.bookSourceType",
            "未知 Legado 内容类型，候选规则暂用 mixed。",
            source_type,
        )
    rule: Dict[str, Any] = {
        "id": "legado-" + _digest(identity, 16),
        "name": str(source.get("bookSourceName") or "未命名 Legado 规则").strip(),
        "author": "",
        "host": _derive_host(source),
        "contentType": content_type,
        "enabled": bool(source.get("enabled", True)),
    }
    if source.get("bookSourceGroup") not in (None, ""):
        rule["group"] = str(source["bookSourceGroup"])
    if isinstance(source.get("customOrder"), int):
        rule["sort"] = source["customOrder"]
    if isinstance(source.get("lastUpdateTime"), int):
        rule["modifiedTime"] = source["lastUpdateTime"]
    return rule


def _map_selector_fields(
    rule: Dict[str, Any],
    source_section: Any,
    mapping: Mapping[str, str],
    source_prefix: str,
    diagnostics: List[Diagnostic],
) -> None:
    if not isinstance(source_section, Mapping):
        return
    for source_key, target_key in mapping.items():
        converted = _convert_selector(
            source_section.get(source_key),
            "$.{}.{}".format(source_prefix, source_key),
            diagnostics,
        )
        if converted:
            rule[target_key] = converted


def convert_source(parsed: ParsedSource) -> ConversionResult:
    source = parsed.value
    diagnostics = list(scan_capabilities(source))
    rule = _copy_metadata(source, diagnostics)

    search_url = _convert_address(source.get("searchUrl"), "$.searchUrl", diagnostics)
    if search_url:
        rule["searchUrl"] = search_url
    _map_selector_fields(
        rule,
        source.get("ruleSearch"),
        {
            "bookList": "searchList",
            "name": "searchName",
            "bookUrl": "searchResult",
            "kind": "searchTags",
            "coverUrl": "searchCover",
            "author": "searchAuthor",
            "lastChapter": "searchChapter",
            "intro": "searchDescription",
        },
        "ruleSearch",
        diagnostics,
    )

    _map_selector_fields(
        rule,
        source.get("ruleToc"),
        {
            "chapterList": "chapterList",
            "chapterName": "chapterName",
            "chapterUrl": "chapterResult",
        },
        "ruleToc",
        diagnostics,
    )
    _map_selector_fields(
        rule,
        source.get("ruleContent"),
        {"content": "contentItems"},
        "ruleContent",
        diagnostics,
    )

    search_required = {"searchUrl", "searchList", "searchName", "searchResult"}
    rule["enableSearch"] = search_required.issubset(rule)
    rule["enableDiscover"] = False
    return ConversionResult(source=parsed, rule=rule, diagnostics=diagnostics)
