"""Belge sayfalarını metne çevirir.

Girdi olarak bir klasördeki görüntüleri ya da tek bir PDF'i kabul eder;
her ikisinde de çıktı sayfa sırasına göre dizilmiş Page nesneleridir.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from core.preprocess import prepare, prepare_array

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# Kırpılmış gövde bölgesi "değişken boyutlu tek sütun"dur. Otomatik kip (3)
# burada tabloları çok sütunlu sanıp satırları parçalıyor.
DEFAULT_PSM = 4
PDF_RENDER_SCALE = 3.0  # ~300 DPI; Tesseract'ın istediği çözünürlük.


def find_tesseract() -> str:
    """Tesseract binary'sini bulur."""
    local = Path(__file__).resolve().parent.parent / ".mamba/bin/tesseract"
    if local.exists():
        return str(local)

    import shutil

    found = shutil.which("tesseract")
    if not found:
        raise RuntimeError(
            "Tesseract bulunamadı. Kurulum için:\n"
            "  micromamba create -y -p .mamba -c conda-forge tesseract"
        )
    return found


@dataclass
class Page:
    """Tek bir belge sayfası ve okunan metni."""

    number: int
    source: str
    text: str

    @property
    def is_empty(self) -> bool:
        return len(self.text.split()) < 5


def _run_tesseract(image: np.ndarray, *, lang: str, psm: int) -> str:
    """Hazırlanmış görüntüyü Tesseract'a verip metni alır."""
    binary = find_tesseract()
    encoded = cv2.imencode(".png", image)[1].tobytes()

    result = subprocess.run(
        [binary, "stdin", "stdout", "-l", lang, "--psm", str(psm)],
        input=encoded,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Tesseract hatası: {result.stderr.decode(errors='replace')}")
    return result.stdout.decode("utf-8", errors="replace")


def read_images(folder: Path, *, lang: str = "tur", psm: int = DEFAULT_PSM) -> list[Page]:
    """Bir klasördeki sayfa görüntülerini okur."""
    paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    return [
        Page(number=i, source=p.name, text=_run_tesseract(prepare(p), lang=lang, psm=psm))
        for i, p in enumerate(paths, start=1)
    ]


def read_pdf(path: Path, *, lang: str = "tur", psm: int = DEFAULT_PSM) -> list[Page]:
    """Taranmış bir PDF'in sayfalarını görüntüye çevirip okur."""
    import pypdfium2

    pages = []
    document = pypdfium2.PdfDocument(path)
    try:
        for index, pdf_page in enumerate(document, start=1):
            rendered = pdf_page.render(scale=PDF_RENDER_SCALE).to_numpy()
            image = cv2.cvtColor(rendered, cv2.COLOR_RGB2BGR)
            pages.append(
                Page(
                    number=index,
                    source=f"{path.name}#{index}",
                    text=_run_tesseract(prepare_array(image), lang=lang, psm=psm),
                )
            )
    finally:
        document.close()
    return pages


def read_document(source: Path, **kwargs) -> list[Page]:
    """Klasör ya da PDF ayrımını yapıp uygun okuyucuya yönlendirir."""
    if source.is_dir():
        return read_images(source, **kwargs)
    if source.suffix.lower() == ".pdf":
        return read_pdf(source, **kwargs)
    raise ValueError(f"Desteklenmeyen girdi: {source}")
