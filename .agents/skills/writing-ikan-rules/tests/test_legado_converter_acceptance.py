import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "convert_legado_rules.py"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "legado_mixed_batch.txt"


class LegadoConverterAcceptanceTests(unittest.TestCase):
    def test_public_cli_converts_mixed_batch_without_claiming_live_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "converted"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    str(FIXTURE_PATH),
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            report_text = (output / "conversion-report.json").read_text(
                encoding="utf-8"
            )
            report = json.loads(report_text)
            candidates = [
                path
                for path in output.glob("*.json")
                if path.name != "conversion-report.json"
            ]

        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertEqual(3, len(candidates))
        self.assertEqual(
            {"total": 3, "converted": 2, "partial": 0, "unsupported": 1},
            report["summary"],
        )
        self.assertEqual("not-run", report["networkVerification"])
        self.assertNotIn("private-secret", report_text)
        self.assertTrue(all(item["output"] for item in report["sources"]))


if __name__ == "__main__":
    unittest.main()
