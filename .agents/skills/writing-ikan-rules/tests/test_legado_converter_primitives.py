import unittest
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from legado_converter.converter import convert_source, safe_output_name
from legado_converter.models import ParsedSource, SourceLocation


def parsed(value):
    return ParsedSource(value=value, location=SourceLocation("fixture.json", 1))


class LegadoConverterPrimitiveTests(unittest.TestCase):
    def test_converts_basic_novel_metadata_with_stable_identity(self):
        source = {
            "bookSourceName": "看书君",
            "bookSourceGroup": "youchen",
            "bookSourceType": 0,
            "bookSourceUrl": "https://m.example.com/#note",
            "enabled": True,
            "customOrder": 7,
            "lastUpdateTime": 1234,
        }

        first = convert_source(parsed(source))
        second = convert_source(parsed(source))

        self.assertEqual("看书君", first.rule["name"])
        self.assertEqual("novel", first.rule["contentType"])
        self.assertEqual("https://m.example.com", first.rule["host"])
        self.assertEqual("youchen", first.rule["group"])
        self.assertEqual(7, first.rule["sort"])
        self.assertEqual(1234, first.rule["modifiedTime"])
        self.assertRegex(first.rule["id"], r"^legado-[0-9a-f]{16}$")
        self.assertEqual(first.rule["id"], second.rule["id"])

    def test_maps_known_content_types_and_reports_unknown_values(self):
        expected = {0: "novel", 1: "audio", 2: "manga", 3: "mixed"}
        for source_type, content_type in expected.items():
            result = convert_source(
                parsed(
                    {
                        "bookSourceName": str(source_type),
                        "bookSourceType": source_type,
                        "bookSourceUrl": "https://example.com",
                    }
                )
            )
            self.assertEqual(content_type, result.rule["contentType"])

        unknown = convert_source(
            parsed(
                {
                    "bookSourceName": "unknown",
                    "bookSourceType": 99,
                    "bookSourceUrl": "https://example.com",
                }
            )
        )
        self.assertEqual("mixed", unknown.rule["contentType"])
        self.assertIn(
            "conversion.content_type", {item.code for item in unknown.diagnostics}
        )

    def test_virtual_host_is_not_emitted_as_a_url(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "聚合",
                    "bookSourceUrl": "聚合书源",
                    "searchUrl": "https://api.example.com/search?q={{key}}",
                }
            )
        )

        self.assertEqual("https://api.example.com", result.rule["host"])
        self.assertIn("capability.virtual_host", {item.code for item in result.diagnostics})

    def test_safe_output_names_are_stable_and_identity_specific(self):
        first = safe_output_name("同名 / 规则", "identity-a")
        second = safe_output_name("同名 / 规则", "identity-b")

        self.assertRegex(first, r"^同名-规则-[0-9a-f]{8}\.json$")
        self.assertNotEqual(first, second)
        self.assertEqual(first, safe_output_name("同名 / 规则", "identity-a"))

    def test_converts_get_templates_and_supported_page_arithmetic(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "template",
                    "bookSourceUrl": "https://example.com",
                    "searchUrl": "/search?q={{key}}&page={{page}}&offset={{(page-1)*100}}",
                }
            )
        )

        self.assertEqual(
            "/search?q=$keyword&page=$page&offset=${(page-1)*100}",
            result.rule["searchUrl"],
        )

    def test_converts_legado_post_request_configuration(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "post",
                    "bookSourceUrl": "https://example.com",
                    "searchUrl": '/search/,{"body":"searchkey={{key}}&page={{page}}","method":"POST","headers":{"X-App":"reader"}}',
                }
            )
        )

        request = result.rule["searchUrl"]
        self.assertTrue(request.startswith("@js:"))
        self.assertIn('url:"/search/"', request)
        self.assertIn('method:"POST"', request)
        self.assertIn("${encodeURIComponent(keyword)}", request)
        self.assertIn("${page}", request)
        self.assertIn('"X-App":"reader"', request)

    def test_reports_unsupported_template_instead_of_copying_it(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "unsupported-template",
                    "bookSourceUrl": "https://example.com",
                    "searchUrl": "/search?time={{java.timeFormat(1)}}",
                }
            )
        )

        self.assertNotIn("searchUrl", result.rule)
        self.assertIn(
            "conversion.template_unsupported",
            {item.code for item in result.diagnostics},
        )

    def test_converts_common_selector_forms(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "selectors",
                    "bookSourceUrl": "https://example.com",
                    "ruleSearch": {
                        "bookList": "class.book-item",
                        "name": "tag.a.0@text",
                        "bookUrl": "tag.a.0@href",
                        "author": "$.author",
                    },
                    "ruleToc": {
                        "chapterList": "class.info-chapters.1@a",
                        "chapterName": "text",
                        "chapterUrl": "href",
                    },
                    "ruleContent": {"content": "//div[@id='content']/text()"},
                }
            )
        )

        self.assertEqual(".book-item", result.rule["searchList"])
        self.assertEqual("a:nth-of-type(1)@text", result.rule["searchName"])
        self.assertEqual("a:nth-of-type(1)@href", result.rule["searchResult"])
        self.assertEqual("$.author", result.rule["searchAuthor"])
        self.assertEqual(
            ".info-chapters:nth-of-type(2) a", result.rule["chapterList"]
        )
        self.assertEqual("text", result.rule["chapterName"])
        self.assertEqual("href", result.rule["chapterResult"])
        self.assertEqual("//div[@id='content']/text()", result.rule["contentItems"])


if __name__ == "__main__":
    unittest.main()
