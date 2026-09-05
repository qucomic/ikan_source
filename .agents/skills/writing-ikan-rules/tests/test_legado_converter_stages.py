import json
import unittest
from pathlib import Path
import sys


TEST_DIR = Path(__file__).parent
SCRIPTS_DIR = TEST_DIR.parents[0] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from legado_converter.converter import convert_source
from legado_converter.models import ParsedSource, SourceLocation


def fixture(name):
    path = TEST_DIR / "fixtures" / name
    return ParsedSource(
        value=json.loads(path.read_text(encoding="utf-8")),
        location=SourceLocation(str(path), 1),
    )


def parsed(value):
    return ParsedSource(value=value, location=SourceLocation("fixture.json", 1))


class LegadoConverterStageTests(unittest.TestCase):
    def test_converts_complete_static_search_discover_chapter_and_content(self):
        result = convert_source(fixture("legado_static_novel.json"))

        self.assertTrue(result.rule["enableSearch"])
        self.assertTrue(result.rule["enableDiscover"])
        self.assertEqual(
            "分类::玄幻::/sort/1_$page/\n分类::都市::/sort/2_$page/",
            result.rule["discoverUrl"],
        )
        self.assertEqual(".book", result.rule["discoverList"])
        self.assertEqual(".title@text", result.rule["discoverName"])
        self.assertEqual(".title@href", result.rule["discoverResult"])
        self.assertEqual(".chapters a", result.rule["chapterList"])
        self.assertEqual("#content@text", result.rule["contentItems"])
        self.assertEqual(
            ["search", "discover", "chapter", "content"], result.converted_stages
        )
        self.assertEqual([], result.disabled_stages)

    def test_converts_qimao_style_fake_routes_to_deferred_signed_categories(self):
        result = convert_source(fixture("legado_dynamic_discover.json"))

        discover = result.rule["discoverUrl"]
        self.assertIn("男频::玄幻::@js:apiRequest(", discover)
        self.assertIn("'/api/v4/category/get-list'", discover)
        self.assertIn("category_id:'202'", discover)
        self.assertIn("page:${page}", discover)
        self.assertIn("男频::热血::@js:apiRequest(", discover)
        self.assertIn("'/api/v4/tag/index'", discover)
        self.assertTrue(result.rule["useCryptoJS"])
        self.assertIn("function apiRequest", result.rule["loadJs"])
        self.assertIn("CryptoJS.MD5", result.rule["loadJs"])

    def test_converts_recognized_combined_filter_definition(self):
        explore = json.dumps(
            {
                "url": "/books?sort={{values.sort}}&area={{values.area}}&page={{page}}",
                "rules": [
                    {
                        "name": "排序",
                        "key": "sort",
                        "value": "latest",
                        "options": [
                            {"option": "最新", "value": "latest"},
                            {"option": "最热", "value": "hot"},
                        ],
                    },
                    {
                        "name": "地区",
                        "key": "area",
                        "value": "all",
                        "options": [{"option": "全部", "value": "all"}],
                    },
                ],
            },
            ensure_ascii=False,
        )
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "组合筛选",
                    "bookSourceUrl": "https://example.com",
                    "enabledExplore": True,
                    "exploreUrl": explore,
                    "ruleExplore": {
                        "bookList": "$.books[*]",
                        "name": "$.name",
                        "bookUrl": "$.id",
                    },
                    "ruleToc": {
                        "chapterList": "$.chapters[*]",
                        "chapterName": "$.name",
                        "chapterUrl": "$.id",
                    },
                    "ruleContent": {"content": "$.content"},
                }
            )
        )

        self.assertIn("@@DiscoverRule:", result.rule["discoverUrl"])
        self.assertIn("${values.sort}", result.rule["discoverUrl"])
        self.assertIn("${values.area}", result.rule["discoverUrl"])
        self.assertIn("${page}", result.rule["discoverUrl"])

    def test_disables_opaque_dynamic_discovery_and_reports_it(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "动态发现",
                    "bookSourceUrl": "https://example.com",
                    "enabledExplore": True,
                    "exploreUrl": "<js>source.getVariable(); java.ajax(url);</js>",
                    "ruleExplore": {
                        "bookList": "$.books[*]",
                        "name": "$.name",
                        "bookUrl": "$.id",
                    },
                    "ruleToc": {
                        "chapterList": "$.chapters[*]",
                        "chapterName": "$.name",
                        "chapterUrl": "$.id",
                    },
                    "ruleContent": {"content": "$.content"},
                }
            )
        )

        self.assertFalse(result.rule["enableDiscover"])
        self.assertIn("discover", result.disabled_stages)
        self.assertIn(
            "conversion.discover_script_unsupported",
            {item.code for item in result.diagnostics},
        )

    def test_rewrites_compatible_jslib_md5_and_omits_java_packages(self):
        compatible = convert_source(
            parsed(
                {
                    "bookSourceName": "md5",
                    "bookSourceUrl": "https://example.com",
                    "jsLib": "function sign(value) { return java.md5Encode(value); }",
                }
            )
        )
        unsupported = convert_source(
            parsed(
                {
                    "bookSourceName": "java",
                    "bookSourceUrl": "https://example.com",
                    "jsLib": "new JavaImporter(); Packages.javax.crypto.Cipher;",
                }
            )
        )

        self.assertTrue(compatible.rule["useCryptoJS"])
        self.assertIn("CryptoJS.MD5(value).toString()", compatible.rule["loadJs"])
        self.assertNotIn("loadJs", unsupported.rule)
        self.assertIn(
            "conversion.load_js_unsupported",
            {item.code for item in unsupported.diagnostics},
        )


if __name__ == "__main__":
    unittest.main()
