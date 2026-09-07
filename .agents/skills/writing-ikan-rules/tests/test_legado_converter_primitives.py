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
        self.assertEqual("@css:a@[0]@text", result.rule["searchName"])
        self.assertEqual("@css:a@[0]@href", result.rule["searchResult"])
        self.assertEqual("$.author", result.rule["searchAuthor"])
        self.assertEqual(
            ".info-chapters:nth-of-type(2) a", result.rule["chapterList"]
        )
        self.assertEqual("text", result.rule["chapterName"])
        self.assertEqual("href", result.rule["chapterResult"])
        self.assertEqual("//div[@id='content']/text()", result.rule["contentItems"])

    def test_converts_legado_chained_css_and_compact_indices(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "5书库选择器",
                    "bookSourceUrl": "http://www.shuku520.net",
                    "ruleExplore": {
                        "bookList": ".r@ul@li&&.item",
                        "name": ".s2@text&&a.1@text",
                        "bookUrl": "a.0@href",
                        "kind": ".s1@text&&em.0:1@text",
                    },
                    "ruleToc": {
                        "chapterList": "#content_1 a",
                        "chapterName": "text",
                        "chapterUrl": "href",
                    },
                    "ruleContent": {"content": "#booktxt@p@textNodes"},
                }
            )
        )

        self.assertEqual(".r ul li&&.item", result.rule["discoverList"])
        self.assertEqual(
            ".s2@text&&@css:a@[1]@text", result.rule["discoverName"]
        )
        self.assertEqual("@css:a@[0]@href", result.rule["discoverResult"])
        self.assertEqual(
            ".s1@text&&@css:em@[0:1]@text",
            result.rule["discoverTags"],
        )
        self.assertEqual("@css:#booktxt p@textNodes", result.rule["contentItems"])

    def test_converts_legado_at_chain_to_css_descendants(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "descendant chain",
                    "bookSourceUrl": "https://example.com",
                    "ruleSearch": {
                        "bookList": ".book_box@span",
                        "name": ".title@a@text",
                        "bookUrl": ".title@a@href",
                    },
                    "ruleToc": {
                        "chapterList": ".chapters@li@a",
                        "chapterName": "text",
                        "chapterUrl": "href",
                    },
                    "ruleContent": {"content": "#content@text"},
                }
            )
        )

        self.assertEqual(".book_box span", result.rule["searchList"])
        self.assertEqual(".title a@text", result.rule["searchName"])
        self.assertEqual(".title a@href", result.rule["searchResult"])
        self.assertEqual(".chapters li a", result.rule["chapterList"])

    def test_merges_legado_class_and_id_filters_into_the_current_element(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "current element filters",
                    "bookSourceUrl": "https://example.com",
                    "ruleExplore": {
                        "bookList": "tag.article@class.book@class.featured",
                        "name": "tag.h2@class.title@text",
                        "bookUrl": "tag.a@id.detail@href",
                    },
                    "ruleToc": {
                        "chapterList": ".chapters@tag.a",
                        "chapterName": "text",
                        "chapterUrl": "href",
                    },
                    "ruleContent": {"content": "#content@text"},
                }
            )
        )

        self.assertEqual("article.book.featured", result.rule["discoverList"])
        self.assertEqual("h2.title@text", result.rule["discoverName"])
        self.assertEqual("a#detail@href", result.rule["discoverResult"])
        self.assertEqual(".chapters a", result.rule["chapterList"])

    def test_omits_legado_text_lookup_instead_of_emitting_invalid_css(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "text lookup",
                    "bookSourceUrl": "https://example.com",
                    "ruleToc": {
                        "chapterList": ".chapters a",
                        "chapterName": "text",
                        "chapterUrl": "href",
                    },
                    "ruleContent": {
                        "content": "#content@text",
                        "nextContentUrl": "text.下一页@href",
                    },
                }
            )
        )

        self.assertNotIn("contentNextUrl", result.rule)
        self.assertIn(
            "conversion.selector_unsupported",
            {item.code for item in result.diagnostics},
        )

    def test_converts_legado_direct_text_readers(self):
        for reader in ("ownText", "textNodes"):
            with self.subTest(reader=reader):
                result = convert_source(
                    parsed(
                        {
                            "bookSourceName": reader,
                            "bookSourceUrl": "https://example.com",
                            "ruleToc": {
                                "chapterList": ".chapters a",
                                "chapterName": "text",
                                "chapterUrl": "href",
                            },
                            "ruleContent": {"content": "#content@" + reader},
                        }
                    )
                )

                self.assertEqual(
                    "@css:#content@" + reader, result.rule["contentItems"]
                )

    def test_preserves_result_list_operations_and_interleave(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "result operations",
                    "bookSourceUrl": "https://example.com",
                    "ruleExplore": {
                        "bookList": ".primary[-1:0]%%.secondary[!0,2]",
                        "name": ".name@ownText",
                        "bookUrl": "a@href",
                    },
                    "ruleToc": {
                        "chapterList": ".chapters a",
                        "chapterName": "text",
                        "chapterUrl": "href",
                    },
                    "ruleContent": {"content": "#content@text"},
                }
            )
        )

        self.assertEqual(
            "@css:.primary@[-1:0]%%@css:.secondary@[!0,2]",
            result.rule["discoverList"],
        )
        self.assertEqual("@css:.name@ownText", result.rule["discoverName"])

    def test_omits_legado_state_operations_instead_of_emitting_invalid_css(self):
        result = convert_source(
            parsed(
                {
                    "bookSourceName": "state operation",
                    "bookSourceUrl": "https://example.com",
                    "ruleSearch": {
                        "bookList": ".book",
                        "name": 'class.bookname@text@put:{u:"a.0@href"}',
                        "bookUrl": "a@href",
                    },
                    "ruleToc": {
                        "chapterList": ".chapters a",
                        "chapterName": "text",
                        "chapterUrl": "href",
                    },
                    "ruleContent": {"content": "#content@text"},
                }
            )
        )

        self.assertNotIn("searchName", result.rule)
        self.assertIn(
            "conversion.selector_unsupported",
            {item.code for item in result.diagnostics},
        )


if __name__ == "__main__":
    unittest.main()
