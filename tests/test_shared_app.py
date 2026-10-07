"""Paylaşılan ana arayüz: gerçek arşivi değiştirmeden giriş sınırı testi."""
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class SharedAppTests(unittest.TestCase):
    def test_archive_is_gated_and_logout_hides_it(self):
        with patch.dict(os.environ, {"ARSIV_SHARED": "1"}), \
             patch("core.demo.PASSWORD_FILE", Mock(read_text=lambda: "test-archive-password")), \
             patch("core.store.session") as session, \
             patch("core.store.list_documents", return_value=[]):
            app = AppTest.from_file(APP, default_timeout=20).run()
            self.assertFalse(app.exception)
            session.assert_not_called()
            self.assertEqual(len(app.tabs), 0)
            app.text_input[0].set_value("wrong")
            app.button[0].click().run()
            session.assert_not_called()
            app.text_input[0].set_value("test-archive-password")
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.sidebar.radio[0].options, ["Belge işle", "Kayıtlı belgeler"])
            session.assert_not_called()
            self.assertFalse(any("klasör" in field.label for field in app.text_input))
            self.assertEqual(len(app.get("file_uploader")), 1)
            app.sidebar.radio[0].set_value("Kayıtlı belgeler").run()
            self.assertFalse(app.exception)
            self.assertTrue(session.called)
            app.sidebar.radio[0].set_value("Belge işle").run()
            self.assertFalse(app.exception)
            session.reset_mock()
            app.sidebar.button[0].click().run()
            self.assertEqual(len(app.tabs), 0)
            session.assert_not_called()

    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, {"ARSIV_SHARED": "1"}), \
             patch("core.demo.PASSWORD_FILE", Path("/missing-archive-password")), \
             patch("core.store.session") as session:
            app = AppTest.from_file(APP, default_timeout=20).run()
            self.assertTrue(app.error)
            self.assertEqual(len(app.tabs), 0)
            session.assert_not_called()
