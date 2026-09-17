"""OCR onarımının işe yarayıp yaramadığını ölçer.

Onarım "iyi göründü" diye kabul edilemez. Bu betik aynı sayfaları
onarımlı ve onarımsız işleyip iki şeyi karşılaştırır:

  1. Belgedeki bilinen değerler metinde duruyor mu (kayıp var mı)
  2. Bilinen OCR hataları düzelmiş mi

Ayrıca yapılan bütün değişiklikleri listeler; onarımın neyi değiştirdiği
görünmeden güvenilmemeli.

Kullanım:
    .venv/bin/python tests/onarim_olcum.py data/ornek
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.correct import correct_pages  # noqa: E402
from core.pipeline import read_pages  # noqa: E402
from core.summarize import LocalModel  # noqa: E402

# Belgede geçtiğini bildiğimiz değerler. Onarım bunları bozarsa kayıp sayılır.
KNOWN_VALUES = [
    "582", "700", "650.000", "400", "560.000", "88.000", "6600", "1654",
    "148000", "154729", "7.000", "15.000", "80.000", "13.100", "443", "69",
    "2.450", "1937", "1925",
]

# Bilinen OCR hataları: (bozuk biçim, olması gereken)
KNOWN_ERRORS = [
    ("hazineye iye", "hazineye hediye"),
    ("hazineye düm", "hazineye hediye"),
]


def count_present(text: str, values: list[str]) -> set[str]:
    return {value for value in values if value in text}


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "data/ornek")

    print(f"Sayfalar okunuyor: {source}")
    pages = read_pages(source)
    before = "\n".join(p.text for p in pages)

    print("Onarım çalışıyor…\n")
    with LocalModel() as model:
        results = correct_pages(model, [p.text for p in pages])
    after = "\n".join(r.text for r in results)

    # 1. Değer kaybı
    found_before = count_present(before, KNOWN_VALUES)
    found_after = count_present(after, KNOWN_VALUES)
    lost = found_before - found_after
    gained = found_after - found_before

    print("=" * 64)
    print(f"Bilinen değerler:  önce {len(found_before)}/{len(KNOWN_VALUES)}"
          f"   sonra {len(found_after)}/{len(KNOWN_VALUES)}")
    if lost:
        print(f"  KAYIP: {sorted(lost)}")
    if gained:
        print(f"  kazanılan: {sorted(gained)}")
    if not lost and not gained:
        print("  değişiklik yok — onarım sayıları bozmadı")

    # 2. Bilinen hatalar düzeldi mi
    print("\nBilinen OCR hataları:")
    for broken, expected in KNOWN_ERRORS:
        was = broken in before
        fixed = expected in after
        if was:
            print(f"  {'✓' if fixed else '✗'} '{broken}' → '{expected}'"
                  f" {'düzeldi' if fixed else 'DÜZELMEDİ'}")
    if not any(broken in before for broken, _ in KNOWN_ERRORS):
        print("  (bu belgede bilinen hata yok)")

    # 3. Reddedilen sayfalar
    rejected = [(i, r.reason) for i, r in enumerate(results, 1) if r.rejected]
    print(f"\nReddedilen sayfa: {len(rejected)}/{len(results)}")
    for number, reason in rejected:
        print(f"  sayfa {number}: {reason}")

    # 4. Yapılan değişiklikler
    total = sum(len(r.changes) for r in results)
    print(f"\nToplam değişiklik: {total}")
    for index, result in enumerate(results, 1):
        for old, new in result.changes:
            print(f"  s{index}: {old!r} → {new!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
