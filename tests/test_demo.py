"""Demo sınırları ve oturum izolasyonu; gerçek arşive dokunmaz."""
import io
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from core.demo import DemoQueue, validate_files
from core.summarize import extract_kunye


class DemoTests(unittest.TestCase):
    def test_upload_limits(self):
        for files in ([], [("a.jpg", b"x")] * 16,
                      [("a.jpg", b"x" * (20 * 1024 * 1024 + 1))],
                      [("a.pdf", b"x"), ("b.jpg", b"x")], [("a.py", b"x")]):
            with self.assertRaises(ValueError):
                validate_files(files)

    def test_valid_image(self):
        buffer = io.BytesIO()
        Image.new("RGB", (50, 50), "white").save(buffer, format="PNG")
        validate_files([("../../example.png", buffer.getvalue())])

    def test_corrupt_image(self):
        with self.assertRaises(Exception):
            validate_files([("a.png", b"not an image")])

    def test_auth(self):
        queue = DemoQueue()
        self.assertFalse(queue.authenticate("", ""))
        self.assertFalse(queue.authenticate("wrong", "correct"))
        self.assertTrue(queue.authenticate("correct", "correct"))
        for _ in range(20):
            queue.authenticate("wrong", "correct")
        self.assertFalse(queue.authenticate("correct", "correct"))
        queue.executor.shutdown()

    def test_queue_serial_and_bounded(self):
        queue = DemoQueue()
        gate = threading.Event()
        with patch.object(queue, "process", side_effect=lambda *a, **k: gate.wait(5)):
            try:
                jobs = [queue.submit([]) for _ in range(3)]
                with self.assertRaises(ValueError):
                    queue.submit([])
                self.assertFalse(jobs[1].running())
                self.assertFalse(jobs[2].running())
            finally:
                gate.set()
                for job in jobs:
                    job.result(timeout=5)
        queue.executor.shutdown()

    def test_demo_disables_note_cache(self):
        with patch("core.summarize.build_notes", return_value=["not"]) as notes, \
             patch("core.summarize.kunye_from_text"):
            extract_kunye(object(), ["kelime " * 501], cache_notes=False)
            self.assertFalse(notes.call_args.kwargs["cache"])

    def test_missing_password_fails_closed(self):
        from streamlit.testing.v1 import AppTest
        with patch("core.demo.PASSWORD_FILE", Path("/missing-demo-password")):
            app = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "demo_app.py")).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertEqual(len(app.get("file_uploader")), 0)

    def test_login_and_session_isolation(self):
        from streamlit.testing.v1 import AppTest
        path = str(Path(__file__).resolve().parent.parent / "demo_app.py")
        with patch("core.demo.PASSWORD_FILE", Mock(read_text=lambda: "test-password-not-real")):
            app = AppTest.from_file(path, default_timeout=20).run()
            self.assertEqual(len(app.get("file_uploader")), 0)
            app.text_input[0].set_value("wrong")
            app.button[0].click().run()
            self.assertTrue(app.error)
            self.assertEqual(len(app.get("file_uploader")), 0)
            app.text_input[0].set_value("test-password-not-real")
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get("file_uploader")), 1)
            self.assertEqual(len(app.tabs), 0)
            other = AppTest.from_file(path, default_timeout=20).run()
            self.assertEqual(len(other.get("file_uploader")), 0)
            app.button[0].click().run()
            self.assertEqual(len(app.get("file_uploader")), 0)


if __name__ == "__main__":
    unittest.main()
