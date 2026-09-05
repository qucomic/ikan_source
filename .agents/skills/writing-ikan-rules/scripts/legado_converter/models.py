"""Data models shared by the Legado conversion pipeline."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    field: str
    message: str
    excerpt: str = ""

    def to_dict(self) -> Dict[str, str]:
        value = {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
        }
        if self.excerpt:
            value["excerpt"] = self.excerpt
        return value


@dataclass(frozen=True)
class SourceLocation:
    origin: str
    index: int = 1

    @property
    def label(self) -> str:
        return "{}#{}".format(self.origin, self.index)


@dataclass(frozen=True)
class ParsedSource:
    value: Dict[str, Any]
    location: SourceLocation


@dataclass
class ValidationSummary:
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, List[Dict[str, str]]]:
        return {"errors": self.errors, "warnings": self.warnings}


@dataclass
class ConversionResult:
    source: ParsedSource
    rule: Dict[str, Any]
    diagnostics: List[Diagnostic] = field(default_factory=list)
    converted_stages: List[str] = field(default_factory=list)
    disabled_stages: List[str] = field(default_factory=list)
    validation: ValidationSummary = field(default_factory=ValidationSummary)
    status: str = "partial"
    output: Optional[str] = None

    @property
    def name(self) -> str:
        value = self.source.value.get("bookSourceName")
        return str(value).strip() if value is not None else ""
