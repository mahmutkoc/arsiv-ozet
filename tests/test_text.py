"""Türkçe harf dönüşümü testleri.

Python'un yerleşik lower()/upper() işlevleri Türkçede sessiz hata veriyor
ve bu hatalar kodun her yerine yayılabiliyor. Buradaki testler dönüşümün
kendisini sabitliyor.

Kullanım:
    .venv/bin/python tests/test_text.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clean import is_noise  # noqa: E402
from core.text import fold, turkish_lower, turkish_upper  # noqa: E402


def test_noktali_I_kucultulur() -> None:
    """'İ'.lower() 'i' ile birleşen nokta üretiyor, eşleşmeyi bozuyor.

    'BULGARİSTAN' ülke listesinde bulunamamasının sebebi buydu.
    """
    assert turkish_lower("BULGARİSTAN") == "bulgaristan"
    assert "BULGARİSTAN".lower() != "bulgaristan", "yerleşik lower() düzelmiş, test güncellensin"


def test_noktasiz_I_kucultulur() -> None:
    assert turkish_lower("ISPARTA") == "ısparta"
    assert turkish_lower("IŞIK") == "ışık"


def test_buyutme() -> None:
    assert turkish_upper("istanbul") == "İSTANBUL"
    assert turkish_upper("ışık") == "IŞIK"


def test_gidis_donus() -> None:
    for word in ("İstanbul", "Işık", "Kâtib", "Çiftlik"):
        assert turkish_lower(turkish_upper(word)) == turkish_lower(word)


def test_fold_sapkayi_duzler() -> None:
    """Dönem imlasında şapkalı harf yaygın; karşılaştırmada eşleşmeli."""
    assert fold("KÂTİB") == fold("katib")
    assert fold("  ÂMİL  ") == "amil"


def test_tekrarlanan_turkce_harf_gurultu_sayilir() -> None:
    """'İİİ' tek harfin tekrarı; yerleşik lower() bunu göremiyordu."""
    assert is_noise("İİİ ŞŞŞ")
    assert is_noise("ııı III")
    assert not is_noise("Çifliklerin arazisi ile tesisat")


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
