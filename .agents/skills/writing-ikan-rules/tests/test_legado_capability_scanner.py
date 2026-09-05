import unittest
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from legado_converter.capability_scanner import redact_excerpt, scan_capabilities


class LegadoCapabilityScannerTests(unittest.TestCase):
    def test_scans_android_and_stateful_runtime_dependencies(self):
        source = {
            "bookSourceUrl": "virtual source",
            "jsLib": (
                "source.getVariable(); source.setVariable('x'); "
                "new JavaImporter(); Packages.javax.crypto.Cipher;"
            ),
        }

        codes = {item.code for item in scan_capabilities(source)}

        self.assertIn("capability.virtual_host", codes)
        self.assertIn("capability.source_variable", codes)
        self.assertIn("capability.java_importer", codes)
        self.assertIn("capability.java_packages", codes)

    def test_scans_request_login_browser_and_crypto_features(self):
        source = {
            "loginUi": "source.getLoginInfoMap()",
            "ruleContent": {
                "content": (
                    "java.ajax(url); java.get('x'); java.put('x','y'); "
                    "cookie.getCookie(host); java.startBrowser(url); "
                    "java.md5Encode(text); CryptoJS.AES.decrypt(data, key);"
                )
            },
        }

        codes = {item.code for item in scan_capabilities(source)}

        self.assertTrue(
            {
                "capability.java_ajax",
                "capability.java_storage",
                "capability.login_info",
                "capability.cookie_api",
                "capability.browser_api",
                "capability.crypto",
            }.issubset(codes)
        )

    def test_diagnostics_are_deterministically_ordered(self):
        source = {"z": "java.ajax(x)", "a": "Packages.java.lang.String"}

        diagnostics = scan_capabilities(source)

        self.assertEqual(
            sorted((item.field, item.code) for item in diagnostics),
            [(item.field, item.code) for item in diagnostics],
        )

    def test_redacts_sensitive_structured_and_raw_values(self):
        structured = redact_excerpt(
            {
                "Authorization": "Bearer private-auth",
                "nested": {"token": "private-token"},
                "safe": "visible",
            }
        )
        raw = redact_excerpt(
            "password='private-password'; Cookie: session=private-cookie; safe=visible"
        )

        self.assertNotIn("private-auth", structured)
        self.assertNotIn("private-token", structured)
        self.assertIn("visible", structured)
        self.assertNotIn("private-password", raw)
        self.assertNotIn("private-cookie", raw)
        self.assertIn("[REDACTED]", structured)
        self.assertIn("[REDACTED]", raw)

    def test_redacted_excerpt_is_bounded(self):
        self.assertLessEqual(len(redact_excerpt("x" * 1000, limit=80)), 80)


if __name__ == "__main__":
    unittest.main()
