"""Detect Legado runtime dependencies without executing source scripts."""

import json
import re
from collections.abc import Mapping
from typing import Any, Iterator, List, Tuple
from urllib.parse import urlparse

from .models import Diagnostic


_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|password|passwd|token|secret|api[_-]?key|sign[_-]?key)",
    re.IGNORECASE,
)
_RAW_SECRET = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|token|secret|api[_-]?key|sign[_-]?key)"
    r"(\s*[:=]\s*)([\"']?)([^,;\s\"'}]+)([\"']?)"
)

_CAPABILITIES = (
    ("capability.browser_api", r"\b(?:java\.)?(?:startBrowser|showBrowser|getWebViewUA|webView)\b", "warning", "依赖浏览器或 WebView API。"),
    ("capability.cookie_api", r"\bcookie\.(?:getCookie|setCookie|removeCookie)\b", "warning", "依赖 Legado Cookie API。"),
    ("capability.crypto", r"\b(?:CryptoJS|md5Encode|Base64|AES|Cipher|SecretKeySpec|IvParameterSpec)\b", "info", "包含哈希、编码或加解密逻辑。"),
    ("capability.java_ajax", r"\bjava\.ajax\s*\(", "info", "使用 java.ajax 发起请求。"),
    ("capability.java_importer", r"\bJavaImporter\b", "warning", "依赖 JavaImporter。"),
    ("capability.java_packages", r"\bPackages\.", "warning", "依赖 Java/Android Packages API。"),
    ("capability.java_storage", r"\bjava\.(?:get|put|getString)\s*\(", "info", "使用 Legado 临时变量 API。"),
    ("capability.login_info", r"\b(?:getLoginInfoMap|loginUi|loginUrl)\b", "warning", "依赖 Legado 登录配置或登录信息。"),
    ("capability.source_variable", r"\bsource\.(?:getVariable|setVariable)\s*\(", "warning", "依赖持久化源变量。"),
)


def _walk(value: Any, path: str = "$") -> Iterator[Tuple[str, str]]:
    if isinstance(value, Mapping):
        for key in sorted(value, key=lambda item: str(item)):
            child = "{}.{}".format(path, key)
            yield from _walk(value[key], child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, "{}[{}]".format(path, index))
    elif isinstance(value, str):
        yield path, value


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _RAW_SECRET.sub(
            lambda match: "{}{}[REDACTED]".format(match.group(1), match.group(2)),
            value,
        )
    return value


def redact_excerpt(value: Any, limit: int = 240) -> str:
    if limit <= 0:
        return ""
    redacted = _redact_value(value)
    if isinstance(redacted, str):
        text = redacted
    else:
        text = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1] + "…"


def scan_capabilities(source: Mapping[str, Any]) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    source_url = source.get("bookSourceUrl")
    if isinstance(source_url, str) and source_url.strip():
        parsed = urlparse(source_url.strip().split("#", 1)[0])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            diagnostics.append(
                Diagnostic(
                    code="capability.virtual_host",
                    severity="warning",
                    field="$.bookSourceUrl",
                    message="bookSourceUrl 不是可直接使用的 HTTP(S) host。",
                    excerpt=redact_excerpt(source_url),
                )
            )

    for field, text in _walk(source):
        for code, pattern, severity, message in _CAPABILITIES:
            if re.search(pattern, text, re.IGNORECASE):
                diagnostics.append(
                    Diagnostic(
                        code=code,
                        severity=severity,
                        field=field,
                        message=message,
                        excerpt=redact_excerpt(text),
                    )
                )
    if "loginUi" in source or "loginUrl" in source:
        diagnostics.append(
            Diagnostic(
                code="capability.login_info",
                severity="warning",
                field="$.loginUi" if "loginUi" in source else "$.loginUrl",
                message="包含 Legado 登录入口或交互配置。",
                excerpt=redact_excerpt(source.get("loginUi", source.get("loginUrl", ""))),
            )
        )

    unique = {
        (item.field, item.code): item
        for item in diagnostics
    }
    return [unique[key] for key in sorted(unique)]
