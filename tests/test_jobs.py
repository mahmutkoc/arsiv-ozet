import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch
from core.jobs import JobManager
from core.cancellation import checkpoint


class JobTests(unittest.TestCase):
    def test_refreshed_ui_can_cancel_own_job(self):
        import os
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        owner = 'a' * 64
        gate = threading.Event()
        manager = JobManager(lambda *args: gate.wait(5), Mock())
        manager.submit(owner, Path('.'))
        try:
            with patch.dict(os.environ, {'ARSIV_SHARED':'0'}), patch('core.jobs.JobManager', return_value=manager):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
                app.query_params['islem'] = owner
                app.run()
                self.assertFalse(app.exception)
                cancel = next(b for b in app.button if b.label == 'İşlemi iptal et')
                cancel.click().run()
                self.assertFalse(app.exception)
                self.assertTrue(manager.active.cancel.is_set())
        finally:
            gate.set()
            self.wait(manager)
            st.cache_resource.clear()

    def wait(self, manager):
        deadline = time.monotonic() + 3
        while manager.snapshot('a')[1] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(manager.snapshot('a')[1])

    def test_cancel_keeps_slot_until_worker_exits_and_does_not_save(self):
        gate = threading.Event()
        entered = threading.Event()
        def runner(source, report):
            entered.set()
            gate.wait(2)
            checkpoint()
            return 'partial'
        saver = Mock()
        manager = JobManager(runner, saver)
        folder = Path(tempfile.mkdtemp())
        self.assertTrue(manager.submit('a', folder, folder))
        self.assertTrue(entered.wait(1))
        self.assertFalse(manager.cancel_job('b'))
        self.assertIsNone(manager.snapshot('b')[0])
        self.assertTrue(manager.cancel_job('a'))
        self.assertEqual(manager.snapshot('a')[0]['status'], 'cancelling')
        self.assertFalse(manager.submit('b', Path('.')))
        gate.set()
        self.wait(manager)
        self.assertEqual(manager.snapshot('a')[0]['status'], 'cancelled')
        self.assertFalse(folder.exists())
        saver.assert_not_called()
        self.assertTrue(manager.submit('a', Path('.')))
        self.wait(manager)
        saver.assert_called_once()

    def test_cancel_even_if_runner_does_not_checkpoint(self):
        gate = threading.Event()
        saver = Mock()
        manager = JobManager(lambda *args: gate.wait(2), saver)
        manager.submit('a', Path('.'))
        self.assertTrue(manager.cancel_job('a'))
        gate.set()
        self.wait(manager)
        saver.assert_not_called()

    def test_completion_visible_after_refresh_and_saved_once(self):
        saver = Mock()
        manager = JobManager(lambda *args: 'result', saver)
        manager.submit('a', Path('.'), name='name')
        self.wait(manager)
        for _ in range(3):
            self.assertEqual(manager.snapshot('a')[0]['result'], 'result')
        saver.assert_called_once_with('result', 'name')
        self.assertFalse(manager.cancel_job('a'))

    def test_failure_cleans_temp_and_releases_slot(self):
        folder = Path(tempfile.mkdtemp())
        manager = JobManager(Mock(side_effect=ValueError('private text')), Mock())
        manager.submit('a', folder, folder)
        self.wait(manager)
        self.assertFalse(folder.exists())
        self.assertEqual(manager.snapshot('a')[0]['status'], 'failed')
        self.assertNotIn('private text', manager.snapshot('a')[0]['message'])
        manager.saver.assert_not_called()
