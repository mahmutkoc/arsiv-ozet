"""Paylaşım demosu: sınırlı iş kuyruğu, girdi doğrulama, geçici işlem."""
from __future__ import annotations

import hmac
import io
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
import pypdfium2

from core.pipeline import read_pages
from core.summarize import LocalModel, extract_kunye

ROOT = Path(__file__).resolve().parent.parent
PASSWORD_FILE = ROOT / ".demo/password.txt"
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 15
MAX_PIXELS = 20_000_000
SAMPLE = (
    "Kurgusal deneme belgesidir. 12 Mart 1937. Geyve Belediye Başkanlığına. "
    "Geyve İlkokulu Müdürü Ali Yılmaz, okul kütüphanesi için yüz kitap ve "
    "iki kitaplık talep etmiştir. Belediye Başkanlığı talebin değerlendirilmek "
    "üzere eğitim komisyonuna gönderilmesine karar vermiştir."
)


class DemoQueue:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="demo")
        self.slots = threading.BoundedSemaphore(3)
        self.auth_lock = threading.Lock()
        self.attempts = []
        self.model = None

    def authenticate(self, candidate: str, expected: str) -> bool:
        # Oturum yenilemekle atlanamayan, süreç genelinde deneme sınırı.
        with self.auth_lock:
            now = time.monotonic()
            self.attempts = [t for t in self.attempts if now - t < 60]
            if len(self.attempts) >= 20:
                return False
            self.attempts.append(now)
        return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())

    def submit(self, files, *, sample=False):
        if not self.slots.acquire(blocking=False):
            raise ValueError("Deneme sırası dolu. Birkaç dakika sonra tekrar deneyin.")
        try:
            future = self.executor.submit(self.process, files, sample=sample)
        except BaseException:
            self.slots.release()
            raise
        future.add_done_callback(lambda _: self.slots.release())
        return future

    def process(self, files, *, sample=False):
        if sample:
            texts = [SAMPLE]
        else:
            validate_files(files)
            with tempfile.TemporaryDirectory(prefix="arsiv-demo-") as folder:
                root = Path(folder)
                for index, (name, content) in enumerate(files, 1):
                    # Kullanıcı dosya adı hiçbir zaman sunucu yolu olamaz.
                    path = root / f"{index:03d}{Path(name).suffix.lower()}"
                    path.write_bytes(content)
                source = next(root.glob("*.pdf")) if Path(files[0][0]).suffix.lower() == ".pdf" else root
                texts = [p.text for p in read_pages(source)]
        if self.model is None:
            self.model = LocalModel().__enter__()
        kunye = extract_kunye(self.model, texts, cache_notes=False)
        return kunye, len(texts), sum(len(t.split()) for t in texts)


def validate_files(files):
    if not files or len(files) > MAX_PAGES:
        raise ValueError("1–15 görüntü veya en fazla 15 sayfalık tek PDF yükleyin.")
    if sum(len(data) for _, data in files) > MAX_BYTES:
        raise ValueError("Toplam dosya boyutu 20 MB'ı aşamaz.")
    pdfs = [name for name, _ in files if Path(name).suffix.lower() == ".pdf"]
    if pdfs and len(files) != 1:
        raise ValueError("PDF'i tek başına yükleyin; görüntülerle birlikte yüklemeyin.")
    for name, data in files:
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf":
            with pypdfium2.PdfDocument(data) as document:
                if not 1 <= len(document) <= MAX_PAGES:
                    raise ValueError("PDF en fazla 15 sayfa olabilir.")
                for index in range(len(document)):
                    width, height = document.get_page_size(index)
                    if width <= 0 or height <= 0 or width * height * 9 > MAX_PIXELS:
                        raise ValueError("PDF sayfa boyutları çok büyük.")
        elif suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            with Image.open(io.BytesIO(data)) as picture:
                if picture.width * picture.height > MAX_PIXELS:
                    raise ValueError("Görüntü en fazla 20 megapiksel olabilir.")
                if getattr(picture, "n_frames", 1) != 1:
                    raise ValueError("Çok sayfalı görüntüyü PDF olarak yükleyin.")
                picture.verify()
        else:
            raise ValueError("Desteklenmeyen dosya türü.")
