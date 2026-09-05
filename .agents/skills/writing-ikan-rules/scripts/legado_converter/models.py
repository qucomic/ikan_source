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

    def to_report_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "input": self.source.location.label,
            "output": self.output,
            "status": self.status,
            "convertedStages": self.converted_stages,
            "disabledStages": self.disabled_stages,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "validation": self.validation.to_dict(),
        }


@dataclass
class BatchResult:
    results: List[ConversionResult]
    input_diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def summary(self) -> Dict[str, int]:
        summary = {"total": len(self.results), "converted": 0, "partial": 0, "unsupported": 0}
        for item in self.results:
            summary[item.status] = summary.get(item.status, 0) + 1
        return summary

    @property
    def exit_code(self) -> int:
        if any(item.status != "converted" for item in self.results):
            return 2
        if any(item.severity in {"warning", "error"} for item in self.input_diagnostics):
            return 2
        return 0

    def to_report_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "networkVerification": "not-run",
            "inputDiagnostics": [item.to_dict() for item in self.input_diagnostics],
            "sources": [item.to_report_dict() for item in self.results],
        }
