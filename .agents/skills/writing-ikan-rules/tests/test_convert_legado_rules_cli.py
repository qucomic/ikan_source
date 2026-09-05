import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "convert_legado_rules.py"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("convert_legado_rules", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def complete_source(name="Complete"):
    return {
        "bookSourceName": name,
        "bookSourceType": 0,
        "bookSourceUrl": "https://example.com",
        "enabled": True,
        "searchUrl": "/search?q={{key}}&page={{page}}",
        "ruleSearch": {
            "bookList": ".book",
            "name": ".title@text",
            "bookUrl": ".title@href",
        },
        "ruleToc": {
            "chapterList": ".chapters a",
            "chapterName": "text",
            "chapterUrl": "href",
        },
        "ruleContent": {"content": "#content@text"},
    }


class ConvertLegadoRulesCliTests(unittest.TestCase):
    def test_batch_writes_plain_rules_and_report_without_stopping(self):
        module = load_cli_module()
        partial = {
            "bookSourceName": "Partial",
            "bookSourceType": 0,
            "bookSourceUrl": "virtual",
            "ruleToc": {"chapterList": ".chapter"},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "sources.txt"
            output_path = root / "output"
            input_path.write_text(
                json.dumps(complete_source(), ensure_ascii=False)
                + ",\n"
                + json.dumps(partial, ensure_ascii=False)
                + ",\n42,",
                encoding="utf-8",
            )

            batch = module.run_conversion(input_path, output_path)
            report = json.loads(
                (output_path / "conversion-report.json").read_text(encoding="utf-8")
            )
            rule_files = sorted(
                path for path in output_path.glob("*.json") if path.name != "conversion-report.json"
            )

            self.assertEqual(2, len(batch.results))
            self.assertEqual(2, len(rule_files))
            self.assertTrue(all(isinstance(json.loads(path.read_text()), dict) for path in rule_files))
            self.assertEqual(2, report["summary"]["total"])
            self.assertEqual(1, report["summary"]["converted"])
            self.assertEqual(1, report["summary"]["unsupported"])
            self.assertEqual("input.not_object", report["inputDiagnostics"][0]["code"])
            self.assertTrue(report["sources"][0]["validation"]["errors"] == [])
            self.assertTrue(report["sources"][1]["validation"]["errors"])

    def test_duplicate_sources_receive_distinct_output_paths(self):
        module = load_cli_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = complete_source("Same")
            input_path = root / "sources.json"
            input_path.write_text(json.dumps([source, source]), encoding="utf-8")

            batch = module.run_conversion(input_path, root / "output")

        self.assertEqual(2, len({item.output for item in batch.results}))

    def test_cli_exit_codes_cover_converted_partial_and_batch_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            complete_path = root / "complete.json"
            partial_path = root / "partial.json"
            complete_path.write_text(json.dumps(complete_source()), encoding="utf-8")
            partial = complete_source("Partial")
            partial["ruleContent"] = {"content": "<js>Packages.java.lang.String</js>"}
            partial_path.write_text(json.dumps(partial), encoding="utf-8")

            complete_run = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(complete_path), "--output", str(root / "ok")],
                text=True,
                capture_output=True,
                check=False,
            )
            partial_run = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(partial_path), "--output", str(root / "partial")],
                text=True,
                capture_output=True,
                check=False,
            )
            failed_run = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(root / "missing.json"), "--output", str(root / "bad")],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, complete_run.returncode, complete_run.stderr)
        self.assertIn("converted=1", complete_run.stdout)
        self.assertEqual(2, partial_run.returncode, partial_run.stderr)
        self.assertEqual(1, failed_run.returncode)
        self.assertIn("没有可处理的 Legado 规则", failed_run.stderr)


if __name__ == "__main__":
    unittest.main()
