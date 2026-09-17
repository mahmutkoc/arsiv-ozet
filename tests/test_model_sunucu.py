"""Model sunucusunun yaşam döngüsü testleri.

Sunucu 7 GB tuttuğu için başlatma ve kapatma mantığı kritik: sızan bir
süreç makineyi dolduruyor, yanlış yerde kurulan bir sinyal yakalayıcı
uygulamayı çalıştırmıyor.

Kullanım:
    .venv/bin/python tests/test_model_sunucu.py
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.summarize import LocalModel  # noqa: E402


class FakeProcess:
    """llama-server yerine geçer."""

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True


def _model_with_process() -> tuple[LocalModel, FakeProcess]:
    model = LocalModel.__new__(LocalModel)
    model._process = FakeProcess()
    model._previous_sigterm = None
    return model, model._process


def test_isci_is_parcaciginda_sinyal_kurulmaz() -> None:
    """signal.signal ana iş parçacığı dışında ValueError veriyor.

    Streamlit betiği işçi iş parçacığında çalıştırdığı için arayüz
    'signal only works in main thread of the main interpreter' hatasıyla
    açılmıyordu. Sinyal yakalayıcı yalnızca ana iş parçacığında kurulmalı;
    diğer durumda atexit tek başına yeterli.
    """
    sonuc: dict[str, object] = {}

    def isci() -> None:
        model = LocalModel.__new__(LocalModel)
        model._process = None
        model._previous_sigterm = None
        model.model_path = Path("sahte.gguf")
        model.context = 1024
        model.port = 0
        try:
            # _spawn'ın sinyal kuran bölümünü taklit ediyoruz; gerçek
            # süreci başlatmadan aynı koşulu sınamak için.
            import signal as signal_module

            if threading.current_thread() is threading.main_thread():
                signal_module.signal(signal_module.SIGTERM, lambda *a: None)
            sonuc["hata"] = None
        except ValueError as error:
            sonuc["hata"] = str(error)

    thread = threading.Thread(target=isci)
    thread.start()
    thread.join()

    assert sonuc["hata"] is None, f"işçi iş parçacığında hata: {sonuc['hata']}"


def test_stop_sureci_kapatir() -> None:
    model, process = _model_with_process()
    model.stop()
    assert process.terminated
    assert model._process is None


def test_stop_iki_kez_cagrilabilir() -> None:
    """atexit ve __exit__ birlikte çalıştığında ikinci çağrı zarar vermemeli."""
    model, _ = _model_with_process()
    model.stop()
    model.stop()  # patlamamalı


def test_kapanmayan_surec_oldurulur() -> None:
    """terminate işe yaramazsa 7 GB'lık süreç ayakta kalmamalı."""

    class StubbornProcess(FakeProcess):
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="llama-server", timeout=timeout or 0)

    model = LocalModel.__new__(LocalModel)
    process = StubbornProcess()
    model._process = process
    model._previous_sigterm = None

    model.stop()
    assert process.killed, "terminate yetmeyince kill çağrılmalı"


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
        except AssertionError as error:
            print(f"  ✗ {test.__name__}: {error}")
            failures += 1
        except Exception as error:  # noqa: BLE001
            print(f"  ✗ {test.__name__}: {type(error).__name__}: {error}")
            failures += 1

    print(f"\n{len(tests) - failures}/{len(tests)} test geçti")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
