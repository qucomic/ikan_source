#!/usr/bin/env python3
"""Convert Legado source batches into offline Ikan rule candidates."""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from legado_converter.converter import convert_source, safe_output_name
from legado_converter.input_parser import load_inputs
from legado_converter.models import BatchResult, ConversionResult, ValidationSummary


VALIDATOR_PATH = SCRIPT_DIR / "validate_rule.py"


class BatchInputError(RuntimeError):
    pass


def _load_validator():
    spec = importlib.util.spec_from_file_location("ikan_rule_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 Ikan 规则验证器。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        Path(temporary_name).replace(path)
    except BaseException:
        try:
            Path(temporary_name).unlink()
        except OSError:
            pass
        raise


def _unique_output_name(proposed: str, used: Set[str]) -> str:
    if proposed not in used:
        used.add(proposed)
        return proposed
    path = Path(proposed)
    index = 2
    while True:
        candidate = "{}-{}{}".format(path.stem, index, path.suffix)
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def _validate(result: ConversionResult, validator: Any) -> None:
    errors = []
    warnings = []
    for issue in validator.validate_document(result.rule):
        record = {"level": issue.level, "field": issue.field, "message": issue.message}
        if issue.level == "error":
            errors.append(record)
        else:
            warnings.append(record)
    result.validation = ValidationSummary(errors=errors, warnings=warnings)


def _assign_status(result: ConversionResult) -> None:
    meaningful = {"chapter", "content"}.issubset(result.converted_stages)
    blocking_diagnostic = any(
        item.severity in {"warning", "error"}
        and item.code.startswith(("conversion.", "capability."))
        for item in result.diagnostics
    )
    if not meaningful:
        result.status = "unsupported"
    elif result.disabled_stages or result.validation.errors or blocking_diagnostic:
        result.status = "partial"
    else:
        result.status = "converted"


def run_conversion(input_path: Path, output_dir: Path) -> BatchResult:
    sources, input_diagnostics = load_inputs(input_path)
    if not sources:
        raise BatchInputError("没有可处理的 Legado 规则。")

    validator = _load_validator()
    results = []
    used_names: Set[str] = set()
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        result = convert_source(source)
        _validate(result, validator)
        _assign_status(result)
        identity = str(source.value.get("bookSourceName", "")) + "\n" + str(
            source.value.get("bookSourceUrl", "")
        )
        filename = _unique_output_name(
            safe_output_name(result.name, identity), used_names
        )
        result.output = filename
        _atomic_write(output_dir / filename, _json_text(result.rule))
        results.append(result)

    batch = BatchResult(results=results, input_diagnostics=input_diagnostics)
    _atomic_write(
        output_dir / "conversion-report.json", _json_text(batch.to_report_dict())
    )
    return batch


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Legado JSON/TXT 文件或目录")
    parser.add_argument("--output", required=True, type=Path, help="Ikan 候选规则输出目录")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        batch = run_conversion(args.input, args.output)
    except (BatchInputError, OSError, UnicodeError, RuntimeError) as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1
    summary = batch.summary
    print(
        "total={total} converted={converted} partial={partial} unsupported={unsupported}".format(
            **summary
        )
    )
    print("report={}".format(args.output / "conversion-report.json"))
    return batch.exit_code


if __name__ == "__main__":
    sys.exit(main())
