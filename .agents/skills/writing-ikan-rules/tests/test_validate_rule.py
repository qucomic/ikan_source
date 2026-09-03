import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "validate_rule.py"
SPEC = importlib.util.spec_from_file_location("validate_rule", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def fields_for(issues, level):
    return {issue.field for issue in issues if issue.level == level}


class ValidateRuleTests(unittest.TestCase):
    def test_accepts_a_minimal_novel_rule_without_dialect_warnings(self):
        rule = {
            "id": "fiction-example",
            "name": "示例小说源",
            "host": "https://fiction.example",
            "contentType": "novel",
            "enableSearch": True,
            "searchUrl": "/search?q=$keyword&page=$page",
            "searchList": ".book-item",
            "searchName": ".title@text",
            "searchResult": ".title@href",
            "enableDiscover": False,
            "chapterList": "#chapters li",
            "chapterName": "a@text",
            "chapterResult": "a@href",
            "contentItems": "#content p@text",
        }

        issues = VALIDATOR.validate_document(rule)

        self.assertEqual([], [issue for issue in issues if issue.level == "error"])
        self.assertEqual([], [issue for issue in issues if issue.level == "warning"])

    def test_rejects_subscription_arrays_instead_of_plain_rule_objects(self):
        issues = VALIDATOR.validate_document(["ikan://encoded"])

        self.assertIn("$", fields_for(issues, "error"))

    def test_reports_missing_enabled_stage_fields(self):
        rule = {
            "id": "incomplete",
            "name": "不完整规则",
            "host": "https://example.com",
            "contentType": 1,
            "enableSearch": True,
            "enableDiscover": True,
        }

        issues = VALIDATOR.validate_document(rule)
        error_fields = fields_for(issues, "error")

        self.assertTrue(
            {
                "searchUrl",
                "searchList",
                "searchName",
                "searchResult",
                "discoverUrl",
                "discoverList",
                "discoverName",
                "discoverResult",
                "chapterList",
                "chapterName",
                "chapterResult|chapterPayload",
                "contentItems",
            }.issubset(error_fields)
        )

    def test_rejects_invalid_content_type_and_non_https_ad_url(self):
        rule = {
            "id": "bad-metadata",
            "name": "错误元数据",
            "host": "https://example.com",
            "contentType": "comic",
            "enableSearch": False,
            "enableDiscover": False,
            "chapterList": ".chapters li",
            "chapterName": "a@text",
            "chapterResult": "a@href",
            "contentItems": "#content@text",
            "adUrl": "http://example.com/ads.json",
        }

        issues = VALIDATOR.validate_document(rule)

        self.assertIn("contentType", fields_for(issues, "error"))
        self.assertIn("adUrl", fields_for(issues, "error"))

    def test_rejects_json_shaped_dynamic_request_without_js_prefix(self):
        rule = {
            "id": "bad-request",
            "name": "错误请求",
            "host": "https://example.com",
            "contentType": 0,
            "enableSearch": True,
            "searchUrl": '{"url":"/api/search","method":"post","body":{"q":"${keyword}"}}',
            "searchList": "$.data.items[*]",
            "searchName": "$.title",
            "searchResult": "$.id",
            "enableDiscover": False,
            "chapterUrl": "@js:`/api/manga/${encodeURIComponent(result)}/chapters`",
            "chapterList": "$.chapters[*]",
            "chapterName": "$.name",
            "chapterResult": "$.id",
            "contentUrl": "@js:`/api/chapter/${encodeURIComponent(result)}`",
            "contentItems": "$.images[*]",
        }

        issues = VALIDATOR.validate_document(rule)

        self.assertIn("searchUrl", fields_for(issues, "error"))

    def test_warns_about_legacy_fields_and_dollar_variables_inside_js(self):
        rule = {
            "id": "warnings",
            "name": "警告规则",
            "host": "https://example.com",
            "contentType": 2,
            "enableSearch": True,
            "searchUrl": "@js:'/search?q=' + $keyword",
            "searchList": "$.items[*]",
            "searchName": "$.name",
            "searchResult": "$.id",
            "enableDiscover": False,
            "chapterList": "$.chapters[*]",
            "chapterName": "$.name",
            "chapterResult": "$.id",
            "contentItems": "$.url",
            "searchItems": "$.items[*]",
        }

        issues = VALIDATOR.validate_document(rule)
        warning_fields = fields_for(issues, "warning")

        self.assertIn("searchUrl", warning_fields)
        self.assertIn("searchItems", warning_fields)

    def test_rejects_css_pseudo_classes_not_supported_by_the_rule_engine(self):
        rule = {
            "id": "unsupported-selector",
            "name": "不支持的选择器",
            "host": "https://example.com",
            "contentType": "manga",
            "enableSearch": True,
            "searchUrl": "/search?q=$keyword",
            "searchList": ".card:has(a)",
            "searchName": "a@text",
            "searchCover": "img::before",
            "searchResult": "a@href",
            "enableDiscover": False,
            "chapterList": ".chapters>a:last-of-type",
            "chapterName": "@text",
            "chapterResult": "@href",
            "contentItems": ".reader>img:nth-of-type(2n+1)@src",
        }

        issues = VALIDATOR.validate_document(rule)

        self.assertIn("searchList", fields_for(issues, "error"))
        self.assertIn("searchCover", fields_for(issues, "error"))
        self.assertNotIn("chapterList", fields_for(issues, "error"))
        self.assertNotIn("contentItems", fields_for(issues, "error"))

    def test_warns_when_current_node_readers_use_compatibility_at_sign(self):
        rule = {
            "id": "current-node-readers",
            "name": "当前节点取值",
            "host": "https://example.com",
            "contentType": "manga",
            "enableSearch": False,
            "enableDiscover": False,
            "chapterList": "#chapters a",
            "chapterName": "@text",
            "chapterResult": "@href",
            "contentItems": ".reader img@src",
        }

        issues = VALIDATOR.validate_document(rule)
        warning_fields = fields_for(issues, "warning")

        self.assertIn("chapterName", warning_fields)
        self.assertIn("chapterResult", warning_fields)

    def test_rejects_full_javascript_inside_waterfall_discover_template(self):
        rule = {
            "id": "unsupported-waterfall-script",
            "name": "不支持的组合筛选脚本",
            "host": "https://example.com",
            "contentType": "manga",
            "enableSearch": False,
            "enableDiscover": True,
            "discoverUrl": """@js:
(() => {
  const query = [['sort', values.sort]]
    .filter(([, value]) => value !== '')
    .map(([key, value]) => `${key}=${value}`);
  query.push(`page=${page}`);
  return `${host}/comics?${query.join('&')}`;
})()
@@DiscoverRule:
{"rules":[{"name":"排序","key":"sort","value":"","options":[{"option":"最新","value":""},{"option":"热门","value":"-views"}]},{"name":"地区","key":"filter[country]","value":"","options":[{"option":"所有","value":""},{"option":"日本","value":"japan"}]}]}
""",
            "discoverList": ".card",
            "discoverName": "a@text",
            "discoverResult": "a@href",
            "chapterList": ".chapters a",
            "chapterName": "text",
            "chapterResult": "href",
            "contentItems": ".reader img@src",
        }

        issues = VALIDATOR.validate_document(rule)

        self.assertIn("discoverUrl", fields_for(issues, "error"))

    def test_accepts_supported_waterfall_discover_template(self):
        rule = {
            "id": "supported-waterfall-template",
            "name": "支持的组合筛选模板",
            "host": "https://example.com",
            "contentType": "manga",
            "enableSearch": False,
            "enableDiscover": True,
            "discoverUrl": """@js:
`${host}/comics?${params.join("&")}&page=${page}`
@@DiscoverRule:
{"rules":[{"name":"排序","key":"sort","value":"","options":[{"option":"最新","value":""},{"option":"热门","value":"-views"}]},{"name":"地区","key":"filter[country]","value":"","options":[{"option":"所有","value":""},{"option":"日本","value":"japan"}]}]}
""",
            "discoverList": ".card",
            "discoverName": "a@text",
            "discoverResult": "a@href",
            "chapterList": ".chapters a",
            "chapterName": "text",
            "chapterResult": "href",
            "contentItems": ".reader img@src",
        }

        issues = VALIDATOR.validate_document(rule)

        self.assertNotIn("discoverUrl", fields_for(issues, "error"))

    def test_requires_road_selectors_when_multi_roads_are_enabled(self):
        rule = {
            "id": "missing-multi-road-fields",
            "name": "缺少多线路字段",
            "host": "https://example.com",
            "contentType": "video",
            "enableSearch": False,
            "enableDiscover": False,
            "enableMultiRoads": True,
            "chapterList": ".episodes a",
            "chapterName": "text",
            "chapterResult": "href",
            "contentItems": "video@src",
        }

        issues = VALIDATOR.validate_document(rule)
        error_fields = fields_for(issues, "error")

        self.assertIn("chapterRoads", error_fields)
        self.assertIn("chapterRoadName", error_fields)

    def test_accepts_complete_multi_road_chapter_rules(self):
        rule = {
            "id": "complete-multi-road-rule",
            "name": "完整多线路规则",
            "host": "https://example.com",
            "contentType": "video",
            "enableSearch": False,
            "enableDiscover": False,
            "enableMultiRoads": True,
            "chapterRoads": ".play-lines .line",
            "chapterRoadName": ".line-title@text",
            "chapterList": ".episodes a",
            "chapterName": "text",
            "chapterResult": "href",
            "contentItems": "video@src",
        }

        issues = VALIDATOR.validate_document(rule)

        self.assertEqual([], [issue for issue in issues if issue.level == "error"])
        self.assertEqual([], [issue for issue in issues if issue.level == "warning"])

    def test_warns_about_road_selectors_when_multi_roads_are_disabled(self):
        rule = {
            "id": "disabled-multi-road-rule",
            "name": "关闭的多线路规则",
            "host": "https://example.com",
            "contentType": "video",
            "enableSearch": False,
            "enableDiscover": False,
            "enableMultiRoads": False,
            "chapterRoads": ".play-lines .line",
            "chapterRoadName": ".line-title@text",
            "chapterList": ".episodes a",
            "chapterName": "text",
            "chapterResult": "href",
            "contentItems": "video@src",
        }

        issues = VALIDATOR.validate_document(rule)
        warning_fields = fields_for(issues, "warning")

        self.assertIn("chapterRoads", warning_fields)
        self.assertIn("chapterRoadName", warning_fields)


if __name__ == "__main__":
    unittest.main()
