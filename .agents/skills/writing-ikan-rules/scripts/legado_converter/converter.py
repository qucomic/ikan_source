"""Conservative, offline Legado-to-Ikan rule conversion."""

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

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
    if re.match(r"^text\.[^@]+@", source, re.IGNORECASE):
        _issue(
            diagnostics,
            "conversion.selector_unsupported",
            field,
            "Legado 文本查找规则不能作为 Ikan CSS 选择器或普通地址直接使用。",
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


def _split_top_level(value: str, delimiter: str) -> List[str]:
    parts: List[str] = []
    start = 0
    quote = ""
    escaped = False
    square_depth = 0
    round_depth = 0
    index = 0
    while index < len(value):
        char = value[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char == "[":
            square_depth += 1
        elif char == "]":
            square_depth = max(0, square_depth - 1)
        elif char == "(":
            round_depth += 1
        elif char == ")":
            round_depth = max(0, round_depth - 1)
        elif square_depth == 0 and round_depth == 0 and value.startswith(
            delimiter, index
        ):
            parts.append(value[start:index])
            parts.append(delimiter)
            index += len(delimiter)
            start = index
            continue
        index += 1
    parts.append(value[start:])
    return parts


def _convert_position(selector: str) -> Optional[str]:
    match = re.fullmatch(r"(.+?)\.(-?\d+)(?::(-?\d+))?", selector)
    if not match:
        return selector
    base, start_text, end_text = match.groups()
    start = int(start_text)
    if end_text is None:
        if start == -1:
            return base + ":last-of-type"
        if start < 0:
            return None
        return base + ":nth-of-type({})".format(start + 1)

    end = int(end_text)
    if start < 0 or end < -1 or (end != -1 and end < start):
        return None
    if start == 0 and end == -1:
        return base
    if end == -1:
        return base + ":nth-of-type(n+{})".format(start + 1)
    if start == end:
        return base + ":nth-of-type({})".format(start + 1)
    upper = ":nth-of-type(-n+{})".format(end + 1)
    if start == 0:
        return base + upper
    return base + ":nth-of-type(n+{})".format(start + 1) + upper


def _extract_result_operation(selector: str) -> Tuple[str, Optional[str]]:
    bracket = re.fullmatch(
        r"(.+?)(\[(?:!)?-?\d*(?::-?\d*(?::-?\d+)?)?(?:,-?\d*(?::-?\d*(?::-?\d+)?)?)*\])",
        selector,
    )
    if bracket and re.search(r"\d", bracket.group(2)):
        return bracket.group(1), bracket.group(2)

    compact = re.fullmatch(r"(.+?)\.(-?\d+(?::-?\d+(?::-?\d+)?)?)", selector)
    if compact:
        return compact.group(1), "[{}]".format(compact.group(2))
    return selector, None


def _convert_css_node(value: str) -> Optional[str]:
    node = value.strip()
    match = re.fullmatch(r"(class|tag|id)\.(.+)", node)
    if match:
        kind, body = match.groups()
        position_match = re.fullmatch(r"(.+?)\.(-?\d+(?::-?\d+)?)", body)
        if position_match:
            body, position = position_match.groups()
        else:
            position = None
        names = body.split()
        if not names or any(not re.fullmatch(r"[\w-]+", name) for name in names):
            return None
        if kind == "class":
            node = "".join("." + name for name in names)
        elif kind == "id":
            if len(names) != 1:
                return None
            node = "#" + names[0]
        else:
            if len(names) != 1:
                return None
            node = names[0]
        if position is not None:
            node += "." + position
    if "!" in node:
        return None
    return _convert_position(node)


def _convert_css_branch(value: str, *, list_selector: bool) -> Optional[str]:
    selector_rule, separator, replacement = value.partition("##")
    explicit_css = selector_rule.lstrip().lower().startswith("@css:")
    if explicit_css:
        selector_rule = selector_rule.lstrip()[len("@css:") :]
    selector_rule = re.sub(r"\s+@(textNodes|text|html|outerHtml|href|src|[\w-]+)\s*$", r"@\1", selector_rule)
    if re.search(r"@(put|get):", selector_rule, re.IGNORECASE):
        return None

    if selector_rule in {"text", "html", "outerHtml", "href", "src"}:
        converted = selector_rule
    elif selector_rule.startswith("@") and re.fullmatch(r"@[A-Za-z][\w-]*", selector_rule):
        converted = selector_rule[1:]
    else:
        chain = _split_top_level(selector_rule, "@")
        tokens = [part.strip() for part in chain if part != "@"]
        if not tokens or re.match(r"^text\.[^@]+$", tokens[0], re.IGNORECASE):
            return None
        if any(
            token in {"text", "html", "outerHtml", "ownText", "textNodes"}
            for token in tokens[:-1]
        ):
            return None
        reader = ""
        if len(tokens) > 1:
            terminal = tokens[-1]
            if terminal == "all":
                return None
            if terminal in {"ownText", "textNodes"}:
                reader = "@" + terminal
                tokens.pop()
            elif terminal in {"text", "html", "outerHtml", "href", "src"} or not list_selector and re.fullmatch(
                r"[A-Za-z_][\w-]*", terminal
            ) and terminal not in {
                "a", "article", "body", "dd", "div", "dl", "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6", "header", "i", "img", "li", "main", "ol", "option", "p", "section", "span", "strong", "table", "tbody", "td", "th", "thead", "tr", "ul"
            }:
                reader = "@" + terminal
                tokens.pop()
        operation = None
        if tokens:
            tokens[-1], operation = _extract_result_operation(tokens[-1])
        converted_nodes = [_convert_css_node(token) for token in tokens]
        if not converted_nodes or any(node is None for node in converted_nodes):
            return None
        converted = ">".join(str(node) for node in converted_nodes)
        if operation:
            converted += "@" + operation
        converted += reader
        if explicit_css or operation or reader in {"@ownText", "@textNodes"}:
            converted = "@css:" + converted
    if separator:
        converted += separator + replacement
    return converted


def _convert_selector(
    value: Any, field: str, diagnostics: List[Diagnostic]
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    source = value.strip()
    if source.startswith("<XPath>"):
        return "@xpath:" + source[len("<XPath>") :].strip()
    if re.search(r"(?:<js>|@js:)", source, re.IGNORECASE):
        _issue(
            diagnostics,
            "conversion.selector_unsupported",
            field,
            "选择器脚本需要专门转换。",
            source,
        )
        return None
    if "{{" in source:
        expressions = [match.group(1).strip() for match in _TEMPLATE.finditer(source)]
        if expressions and all(
            expression.startswith(("$", ".", "//", "@css:", "@json:", "@xpath:"))
            for expression in expressions
        ):
            return source
        _issue(
            diagnostics,
            "conversion.selector_unsupported",
            field,
            "复合模板选择器无法可靠离线转换。",
            source,
        )
        return None
    branches = _split_top_level(source, "&&")
    expanded: List[str] = []
    for branch in branches:
        if branch == "&&":
            expanded.append(branch)
        else:
            fallback_parts = _split_top_level(branch, "||")
            for fallback_part in fallback_parts:
                if fallback_part == "||":
                    expanded.append(fallback_part)
                else:
                    expanded.extend(_split_top_level(fallback_part, "%%"))
    converted: List[str] = []
    for part in expanded:
        if part in {"&&", "||", "%%"}:
            converted.append(part)
            continue
        branch = part.strip()
        if branch.startswith(("$", "//", "@json:", "@xpath:")):
            converted.append(branch)
            continue
        css = _convert_css_branch(
            branch,
            list_selector=field.endswith((".bookList", ".chapterList")),
        )
        if css is None:
            _issue(
                diagnostics,
                "conversion.selector_unsupported",
                field,
                "Legado 选择器无法可靠转换为 Ikan 规则。",
                source,
            )
            return None
        converted.append(css)
    return "".join(converted)


def _convert_address_or_selector(
    value: Any, field: str, diagnostics: List[Diagnostic]
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    source = value.strip()
    if source.lower().startswith(("http://", "https://")) or (
        source.startswith(("/", "./", "../")) and not source.startswith("//")
    ):
        return _convert_address(source, field, diagnostics)
    if (
        "@" in source
        or source.startswith((".", "#", "[", "//", "$"))
        or re.match(r"^(?:class|tag|id|text)\.", source, re.IGNORECASE)
    ):
        return _convert_selector(source, field, diagnostics)
    return _convert_address(source, field, diagnostics)


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


def _convert_load_js(
    source: Mapping[str, Any], diagnostics: List[Diagnostic]
) -> Tuple[str, bool]:
    raw = source.get("jsLib")
    if not isinstance(raw, str) or not raw.strip():
        return "", False
    unsupported = re.search(
        r"\b(?:JavaImporter|Packages\.|java\.ajax|source\.|cookie\.|java\.(?:startBrowser|showBrowser|getWebViewUA))",
        raw,
    )
    if unsupported:
        _issue(
            diagnostics,
            "conversion.load_js_unsupported",
            "$.jsLib",
            "jsLib 依赖无法离线迁移的 Legado Java/Android API。",
            raw,
        )
        return "", False
    converted = re.sub(
        r"\bjava\.md5Encode\(\s*([^()]+?)\s*\)",
        r"CryptoJS.MD5(\1).toString()",
        raw,
    )
    if re.search(r"\bjava\.", converted):
        _issue(
            diagnostics,
            "conversion.load_js_unsupported",
            "$.jsLib",
            "jsLib 仍包含未识别的 java API。",
            raw,
        )
        return "", False
    return converted.strip(), "CryptoJS" in converted


def _extract_sign_key(source: Mapping[str, Any]) -> Optional[str]:
    pattern = re.compile(r"\bsign_key\s*=\s*['\"]([^'\"]+)['\"]")
    for text in _walk_strings(source):
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _static_headers(source: Mapping[str, Any]) -> Dict[str, str]:
    value = source.get("header")
    if not isinstance(value, str):
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in decoded.items()
        if isinstance(item, (str, int, float, bool))
    }


def _qimao_api_request_helper(sign_key: str, headers: Mapping[str, str]) -> str:
    return """function apiRequest(base, path, params) {
  const signKey = %s;
  const values = Object.assign({}, params);
  const canonical = Object.keys(values).sort().map(key => key + '=' + values[key]).join('');
  values.sign = CryptoJS.MD5(canonical + signKey).toString();
  const requestHeaders = Object.assign({}, %s);
  if (Object.keys(requestHeaders).length) {
    const headerCanonical = Object.keys(requestHeaders).sort().map(key => key + '=' + requestHeaders[key]).join('');
    requestHeaders.sign = CryptoJS.MD5(headerCanonical + signKey).toString();
  }
  const query = Object.keys(values).map(key => encodeURIComponent(key) + '=' + encodeURIComponent(values[key])).join('&');
  return {url: base + path + '?' + query, headers: requestHeaders};
}""" % (
        json.dumps(sign_key, ensure_ascii=False),
        json.dumps(dict(headers), ensure_ascii=False, separators=(",", ":")),
    )


def _qimao_category_address(
    value: str, source: Mapping[str, Any]
) -> Optional[Tuple[str, str]]:
    if "api-bc.wtzw.com" not in str(source.get("bookSourceUrl", "")):
        return None
    parsed = urlparse(value)
    route = None
    raw_params = ""
    if "/category/" in parsed.path:
        route = "/api/v4/category/get-list"
        raw_params = parsed.path.split("/category/", 1)[1]
    elif "/tag/" in parsed.path:
        route = "/api/v4/tag/index"
        raw_params = parsed.path.split("/tag/", 1)[1]
    if route is None:
        return None
    if parsed.query:
        raw_params += ("&" if raw_params else "") + parsed.query
    params = [(key, item) for key, item in parse_qsl(raw_params) if key != "page"]
    rendered = ["{}:{}".format(key, json.dumps(item, ensure_ascii=False).replace('"', "'")) for key, item in params]
    rendered.append("page:${page}")
    return route, "@js:apiRequest('https://api-bc.wtzw.com', %s, {%s})" % (
        json.dumps(route).replace('"', "'"),
        ",".join(rendered),
    )


def _convert_combined_discover(
    config: Mapping[str, Any], diagnostics: List[Diagnostic]
) -> Optional[str]:
    url = config.get("url")
    rules = config.get("rules")
    if not isinstance(url, str) or not isinstance(rules, list):
        return None
    if not all(
        isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("key"), str)
        and isinstance(item.get("options"), list)
        for item in rules
    ):
        _issue(
            diagnostics,
            "conversion.discover_filter_unsupported",
            "$.exploreUrl",
            "组合筛选定义缺少 name/key/options。",
            config,
        )
        return None
    expression = url
    expression = re.sub(
        r"\{\{\s*values\.([A-Za-z_$][\w$]*)\s*\}\}",
        r"${values.\1}",
        expression,
    )
    expression = expression.replace("{{page}}", "${page}")
    if "{{" in expression:
        _issue(
            diagnostics,
            "conversion.discover_filter_unsupported",
            "$.exploreUrl",
            "组合筛选地址包含未知模板。",
            url,
        )
        return None
    return "@js:\n`%s`\n@@DiscoverRule:\n%s" % (
        expression.replace("`", r"\`"),
        json.dumps({"rules": rules}, ensure_ascii=False, separators=(",", ":")),
    )


def _convert_discover(
    source: Mapping[str, Any], diagnostics: List[Diagnostic]
) -> Tuple[Optional[str], str, bool]:
    raw = source.get("exploreUrl")
    if not isinstance(raw, str) or not raw.strip():
        return None, "", False
    if raw.lstrip().lower().startswith(("<js>", "@js:")):
        _issue(
            diagnostics,
            "conversion.discover_script_unsupported",
            "$.exploreUrl",
            "动态发现脚本无法确定性离线转换。",
            raw,
        )
        return None, "", False
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        converted = _convert_template(raw, "$.exploreUrl", diagnostics)
        return converted, "", False
    if isinstance(decoded, dict):
        return _convert_combined_discover(decoded, diagnostics), "", False
    if not isinstance(decoded, list):
        return None, "", False

    channel = "分类"
    rows: List[str] = []
    used_qimao_adapter = False
    for item in decoded:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        address = item.get("url")
        if not isinstance(address, str) or not address.strip():
            if title:
                channel = title
            continue
        qimao = _qimao_category_address(address, source)
        if qimao is not None:
            _, converted_address = qimao
            used_qimao_adapter = True
        else:
            converted_address = _convert_address(address, "$.exploreUrl", diagnostics)
        if title and converted_address:
            rows.append("{}::{}::{}".format(channel, title, converted_address))
    return ("\n".join(rows) if rows else None), channel, used_qimao_adapter


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
            "status": "searchStatus",
            "lastChapter": "searchChapter",
            "intro": "searchDescription",
        },
        "ruleSearch",
        diagnostics,
    )

    discover_url, _, used_qimao_adapter = _convert_discover(source, diagnostics)
    if discover_url:
        rule["discoverUrl"] = discover_url
    _map_selector_fields(
        rule,
        source.get("ruleExplore"),
        {
            "bookList": "discoverList",
            "name": "discoverName",
            "bookUrl": "discoverResult",
            "kind": "discoverTags",
            "coverUrl": "discoverCover",
            "author": "discoverAuthor",
            "status": "discoverStatus",
            "lastChapter": "discoverChapter",
            "intro": "discoverDescription",
        },
        "ruleExplore",
        diagnostics,
    )

    book_info = source.get("ruleBookInfo")
    if isinstance(book_info, Mapping):
        chapter_url = _convert_address_or_selector(
            book_info.get("tocUrl"), "$.ruleBookInfo.tocUrl", diagnostics
        )
        if chapter_url:
            rule["chapterUrl"] = chapter_url

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
    rule_toc = source.get("ruleToc")
    if isinstance(rule_toc, Mapping):
        next_url = _convert_address_or_selector(
            rule_toc.get("nextTocUrl"), "$.ruleToc.nextTocUrl", diagnostics
        )
        if next_url:
            rule["chapterNextUrl"] = next_url
    _map_selector_fields(
        rule,
        source.get("ruleContent"),
        {"content": "contentItems"},
        "ruleContent",
        diagnostics,
    )

    rule_content = source.get("ruleContent")
    if isinstance(rule_content, Mapping):
        content_url = _convert_address(
            rule_content.get("contentUrl"), "$.ruleContent.contentUrl", diagnostics
        )
        if content_url:
            rule["contentUrl"] = content_url
        next_content_url = _convert_address_or_selector(
            rule_content.get("nextContentUrl"),
            "$.ruleContent.nextContentUrl",
            diagnostics,
        )
        if next_content_url:
            rule["contentNextUrl"] = next_content_url

    load_js, uses_crypto = _convert_load_js(source, diagnostics)
    if used_qimao_adapter:
        sign_key = _extract_sign_key(source)
        if sign_key:
            helper = _qimao_api_request_helper(sign_key, _static_headers(source))
            load_js = helper + ("\n\n" + load_js if load_js else "")
            uses_crypto = True
        else:
            _issue(
                diagnostics,
                "conversion.qimao_sign_key_missing",
                "$.exploreUrl",
                "识别到七猫签名分类，但没有找到 sign_key。",
            )
            rule.pop("discoverUrl", None)
    if load_js:
        rule["loadJs"] = load_js
    if uses_crypto:
        rule["useCryptoJS"] = True

    search_required = {"searchUrl", "searchList", "searchName", "searchResult"}
    discover_required = {
        "discoverUrl",
        "discoverList",
        "discoverName",
        "discoverResult",
    }
    chapter_required = {"chapterList", "chapterName"}
    content_required = {"contentItems"}
    converted_stages: List[str] = []
    disabled_stages: List[str] = []

    search_requested = bool(source.get("searchUrl") or source.get("ruleSearch"))
    rule["enableSearch"] = search_required.issubset(rule)
    if rule["enableSearch"]:
        converted_stages.append("search")
    elif search_requested:
        disabled_stages.append("search")
        _issue(
            diagnostics,
            "conversion.search_incomplete",
            "$.ruleSearch",
            "搜索阶段缺少可转换的 URL、列表、名称或作品结果。",
        )

    discover_requested = bool(source.get("enabledExplore") or source.get("exploreUrl"))
    rule["enableDiscover"] = discover_required.issubset(rule)
    if rule["enableDiscover"]:
        converted_stages.append("discover")
    elif discover_requested:
        disabled_stages.append("discover")
        if not any(item.code.startswith("conversion.discover_") for item in diagnostics):
            _issue(
                diagnostics,
                "conversion.discover_incomplete",
                "$.ruleExplore",
                "发现阶段缺少可转换的 URL、列表、名称或作品结果。",
            )

    if chapter_required.issubset(rule) and (
        "chapterResult" in rule or "chapterPayload" in rule
    ):
        converted_stages.append("chapter")
    else:
        _issue(
            diagnostics,
            "conversion.chapter_incomplete",
            "$.ruleToc",
            "目录阶段缺少章节列表、名称或章节结果。",
            source.get("ruleToc", ""),
            severity="error",
        )

    if content_required.issubset(rule):
        converted_stages.append("content")
    else:
        _issue(
            diagnostics,
            "conversion.content_incomplete",
            "$.ruleContent",
            "正文阶段缺少可转换的内容规则。",
            source.get("ruleContent", ""),
            severity="error",
        )

    return ConversionResult(
        source=parsed,
        rule=rule,
        diagnostics=diagnostics,
        converted_stages=converted_stages,
        disabled_stages=disabled_stages,
    )
