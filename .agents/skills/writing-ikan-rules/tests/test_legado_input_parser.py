import tempfile
import unittest
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from legado_converter.input_parser import load_inputs, parse_text


class LegadoInputParserTests(unittest.TestCase):
    def test_parses_single_object_and_standard_array(self):
        single, single_issues = parse_text('{"bookSourceName":"A"}', "one.json")
        batch, batch_issues = parse_text(
            '[{"bookSourceName":"A"},{"bookSourceName":"B"}]', "many.json"
        )

        self.assertEqual(["A"], [item.value["bookSourceName"] for item in single])
        self.assertEqual(["A", "B"], [item.value["bookSourceName"] for item in batch])
        self.assertEqual([], single_issues)
        self.assertEqual([], batch_issues)
        self.assertEqual("many.json#2", batch[1].location.label)

    def test_parses_comma_separated_objects_without_splitting_script_strings(self):
        text = r'''{"bookSourceName":"A","jsLib":"const x = '},{';"},
{"bookSourceName":"B"},'''

        sources, diagnostics = parse_text(text, "batch.txt")

        self.assertEqual(["A", "B"], [item.value["bookSourceName"] for item in sources])
        self.assertEqual([], diagnostics)
        self.assertEqual("batch.txt#2", sources[1].location.label)

    def test_skips_non_object_entries_with_a_diagnostic(self):
        sources, diagnostics = parse_text(
            '[{"bookSourceName":"A"},42,"bad"]', "mixed.json"
        )

        self.assertEqual(1, len(sources))
        self.assertEqual(2, len(diagnostics))
        self.assertTrue(all(item.code == "input.not_object" for item in diagnostics))

    def test_reports_malformed_trailing_content(self):
        sources, diagnostics = parse_text(
            '{"bookSourceName":"A"}, broken', "broken.txt"
        )

        self.assertEqual(1, len(sources))
        self.assertEqual("input.invalid_json", diagnostics[-1].code)
        self.assertEqual("error", diagnostics[-1].severity)

    def test_loads_json_and_txt_files_in_deterministic_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.txt").write_text('{"bookSourceName":"B"}', encoding="utf-8")
            (root / "a.json").write_text('{"bookSourceName":"A"}', encoding="utf-8")
            (root / "ignored.md").write_text('{"bookSourceName":"X"}', encoding="utf-8")

            sources, diagnostics = load_inputs(root)

        self.assertEqual(["A", "B"], [item.value["bookSourceName"] for item in sources])
        self.assertEqual([], diagnostics)


if __name__ == "__main__":
    unittest.main()
