"""OCR, temizleme ve künye çıkarma adımlarını tek akışta birleştirir.

Okuma ve künye çıkarma bilerek ayrı işlevler: dil modeli 7 GB tutuyor ve
OCR sırasında ona hiç ihtiyaç yok. İkisi aynı anda bellekte olunca
16 GB'lık makinede OpenCV görüntü için bellek ayıramayıp sessizce None
dönüyor, bu da "Görüntü okunamadı" hatasına yol açıyordu. Çağıran taraf
önce okuyup sonra modeli açarsa bu darboğaz oluşmuyor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.clean import clean_pages
from core.ocr import Page, read_document
from core.summarize import Kunye, LocalModel, extract_kunye

ProgressCallback = Callable[[str, float], None]


@dataclass
class Result:
    """Bir belgenin işlenmiş hali."""

    name: str
    source: str
    pages: list[Page]
    kunye: Kunye

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def word_count(self) -> int:
        return sum(len(p.text.split()) for p in self.pages)


def _reporter(on_progress: ProgressCallback | None) -> ProgressCallback:
    def report(message: str, fraction: float) -> None:
        if on_progress:
            on_progress(message, fraction)

    return report


def read_pages(source: Path, *, on_progress: ProgressCallback | None = None) -> list[Page]:
    """Belgeyi okuyup metnini temizler. Dil modeli gerekmez."""
    report = _reporter(on_progress)

    report("Sayfalar okunuyor…", 0.1)
    pages = read_document(source)

    report("Metin temizleniyor…", 0.5)
    for page, text in zip(pages, clean_pages([p.text for p in pages])):
        page.text = text

    return pages


def extract(
    source: Path,
    pages: list[Page],
    *,
    model: LocalModel,
    on_progress: ProgressCallback | None = None,
) -> Result:
    """Okunmuş sayfalardan künyeyi çıkarır."""
    report = _reporter(on_progress)

    report("Künye çıkarılıyor…", 0.6)
    kunye = extract_kunye(model, [p.text for p in pages])

    report("Tamamlandı", 1.0)
    return Result(
        name=source.stem or source.name,
        source=str(source),
        pages=pages,
        kunye=kunye,
    )


def process(
    source: Path,
    *,
    model: LocalModel,
    on_progress: ProgressCallback | None = None,
) -> Result:
    """Bir belgeyi baştan sona işler.

    Modeli zaten açık tutan çağıranlar için kolaylık. Belleği korumak
    isteyen çağıran read_pages ve extract'i ayrı ayrı kullanmalı.
    """
    pages = read_pages(source, on_progress=on_progress)
    return extract(source, pages, model=model, on_progress=on_progress)
