"""OCR'ı farklı büyütme ölçeklerinde çalıştırıp doğruluğu karşılaştırır.

Büyütme bazı rakamları düzeltirken başkalarını bozabiliyor. Tek bir örneğe
bakıp karar vermemek için belgedeki bütün bilinen değerleri sayıyoruz.

Kullanım:
    .venv/bin/python tests/olcek_kiyas.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ocr import find_tesseract  # noqa: E402
from core.preprocess import (  # noqa: E402
    crop_to_body,
    deskew,
    normalize_contrast,
    remove_red_stamps,
)

# Belgede gerçekten geçen değerler (kaynak görüntülerden elle doğrulandı).
GROUND_TRUTH = [
    "582", "700", "650.000", "400", "560.000", "88.000", "375", "6600",
    "1654", "2650", "1450", "148000", "154729", "45", "15.000", "7.000",
    "3.000", "14.000", "80.000", "13.100", "443", "69", "2.450", "58",
    "16", "13", "35", "19",
]

SCALES = [1.0, 1.5, 2.0, 2.5, 3.0]


def contains(text: str, value: str) -> bool:
    """Değeri tam sayı olarak arar.

    Düz alt dizi araması yanıltıyor: OCR '688.000' okuduğunda içinde '88.000'
    geçtiği için hata doğru sanılıyor. Bu yüzden sayının önünde ve ardında
    başka rakam olmadığından emin oluyoruz.
    """
    pattern = rf"(?<![\d.]){re.escape(value)}(?![\d.])"
    return re.search(pattern, text) is not None


def ocr_at_scale(paths: list[Path], scale: float, binary: str) -> str:
    """Bütün sayfaları verilen ölçekte okuyup tek metin döndürür."""
    chunks = []
    for path in paths:
        img = crop_to_body(remove_red_stamps(cv2.imread(str(path))))
        if scale != 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        img = normalize_contrast(deskew(img))

        png = cv2.imencode(".png", img)[1].tobytes()
        result = subprocess.run(
            [binary, "stdin", "stdout", "-l", "tur", "--psm", "4"],
            input=png,
            capture_output=True,
        )
        chunks.append(result.stdout.decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def main() -> int:
    binary = find_tesseract()
    paths = sorted(
        p for p in Path("data/ornek").iterdir() if p.suffix.lower() in {".jpeg", ".jpg", ".png"}
    )

    print(f"{len(paths)} sayfa, {len(GROUND_TRUTH)} bilinen değer\n")
    print(f"{'ölçek':<8}{'bulunan':<12}{'kayıp değerler'}")

    for scale in SCALES:
        text = ocr_at_scale(paths, scale, binary)
        missing = [value for value in GROUND_TRUTH if not contains(text, value)]
        found = len(GROUND_TRUTH) - len(missing)
        preview = ", ".join(missing[:8]) or "-"
        print(f"{scale:<8.1f}{found}/{len(GROUND_TRUTH):<9}{preview}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
