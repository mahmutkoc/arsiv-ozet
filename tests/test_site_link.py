import base64
import unittest
from unittest.mock import patch
from core import site_link


class SiteLinkTests(unittest.TestCase):
    def test_fixed_domain(self):
        self.assertEqual(site_link.replace_link("link.href = 'old';", "https://arsiv.mahmutkoc.me"),
                         "link.href = 'https://arsiv.mahmutkoc.me/';")

    def test_changes_only_address(self):
        source = "// keep\n  link.href = 'https://old.trycloudflare.com/';\nlink.target = '_blank';"
        result = site_link.replace_link(source, "https://new-link.trycloudflare.com")
        self.assertEqual(result, source.replace("https://old.trycloudflare.com/", "https://new-link.trycloudflare.com/"))

    def test_rejects_unexpected_input(self):
        with self.assertRaises(ValueError):
            site_link.replace_link("link.href = 'old';", "https://example.com")
        with self.assertRaises(ValueError):
            site_link.replace_link("unknown", "https://valid.trycloudflare.com")

    def test_updates_with_current_sha(self):
        current = {"sha": "latest", "content": base64.b64encode(b"link.href = 'old';").decode()}
        with patch.object(site_link.Path, "read_text", return_value="test-token"), patch.object(site_link, "request", side_effect=[current, {}]) as api:
            ok, _ = site_link.update_site_link("https://new-link.trycloudflare.com")
            self.assertTrue(ok)
            self.assertEqual(api.call_args.args[2]["sha"], "latest")
            self.assertEqual(api.call_args.args[2]["branch"], "main")

    def test_missing_token_does_not_write(self):
        with patch.object(site_link.Path, "read_text", side_effect=FileNotFoundError), patch.object(site_link, "request") as api:
            self.assertFalse(site_link.update_site_link("https://new-link.trycloudflare.com")[0])
            api.assert_not_called()
