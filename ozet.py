"""Komut satırından belge özetleme.

Kullanım:
    .venv/bin/python ozet.py data/ornek
    .venv/bin/python ozet.py belge.pdf --kaydet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import store
from core.pipeline import extract, read_pages
from core.summarize import LocalModel


def main() -> int:
    parser = argparse.ArgumentParser(description="Arşiv belgesini oku ve özetle.")
    parser.add_argument("kaynak", type=Path, help="Sayfa görüntüleri klasörü ya da PDF")
    parser.add_argument("--ad", help="Belge adı (varsayılan: dosya adı)")
    parser.add_argument("--kaydet", action="store_true", help="Sonucu veritabanına yaz")
    parser.add_argument("--metin", action="store_true", help="Sayfa metinlerini de yazdır")
    args = parser.parse_args()

    if not args.kaynak.exists():
        print(f"Bulunamadı: {args.kaynak}", file=sys.stderr)
        return 1

    def report(message: str, fraction: float) -> None:
        print(f"[{fraction:>4.0%}] {message}", file=sys.stderr)

    # Önce oku, sonra modeli aç: 7 GB'lık model bellekteyken OpenCV
    # görüntü için yer bulamayıp okuma başarısız olabiliyor.
    pages = read_pages(args.kaynak, on_progress=report)

    with LocalModel() as model:
        result = extract(args.kaynak, pages, model=model, on_progress=report)

    name = args.ad or result.name
    print(f"\n{'=' * 70}\n{name}  —  {result.page_count} sayfa, {result.word_count} kelime\n{'=' * 70}\n")
    print(result.kunye.as_markdown())

    if args.metin:
        for page in result.pages:
            print(f"\n--- Sayfa {page.number} ({page.source}) ---")
            print(page.text or "(boş)")

    if args.kaydet:
        with store.session() as connection:
            store.save(
                connection,
                ad=name,
                kaynak=str(args.kaynak.resolve()),
                page_texts=[(p.number, p.source, p.text) for p in result.pages],
                ozet=result.kunye.ozet,
                adlar={
                    "yer": result.kunye.yer_adlari,
                    "sahis": result.kunye.sahis_adlari,
                    "kurum": result.kunye.kurum_adlari,
                },
            )
        print(f"\nKaydedildi: {store.DB_PATH}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
