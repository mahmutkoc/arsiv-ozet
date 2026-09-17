"""Özet doğruluğunu belgedeki gerçek değerlerle karşılaştırır.

Model çıktısı serbest metin olduğu için tam eşleşme aranmıyor; sadece
belgedeki kritik sayı ve adların özette geçip geçmediğine bakılıyor.
Amaç, özetleyiciyi değiştirdiğimizde bir gerilemeyi fark etmek.

Kullanım:
    .venv/bin/python tests/dogrulama.py cikti/ozet.txt
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# (etiket, kabul edilen biçimlerden biri yeter, özette olmaması gereken yanlışlar)
# Belge sayıyı bazen yazıyla veriyor ("dört ton", "yüzde kırk"); modelin bunu
# rakama çevirmesi hata değil, o yüzden iki biçim de kabul ediliyor.
CHECKS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("Belge tarihi", ("1937",), ()),
    ("Meyve bahçesi (dönüm)", ("582",), ()),
    ("Fidanlık (dönüm)", ("700",), ()),
    ("Fidan sayısı", ("650.000",), ()),
    ("Amerikan asma (dönüm)", ("400",), ()),
    ("Kök bağ çubuğu", ("560.000",), ()),
    ("Bağ omcası", ("88.000",), ("688.000", "688000")),
    ("Zeytin ağacı", ("6600",), ()),
    ("Portakal ağacı", ("1654",), ()),
    ("Kabili ziraat arazi", ("148000",), ()),
    ("Bira fabrikası (hektolitre)", ("7.000",), ()),
    ("Buz fabrikası (ton)", ("dört ton", "4 ton"), ()),
    ("Süt fabrikası (litre)", ("15.000",), ("25.000", "25000", "30.000")),
    ("Şarap (litre)", ("80.000",), ()),
    ("Çeltik fabrikası hissesi", ("yüzde kırk", "%40", "40 hisse"), ()),
    ("Koyun", ("13.100",), ()),
    ("Sığır", ("443",), ()),
    ("At", ("69",), ()),
    ("Tavuk", ("2.450",), ()),
    ("Traktör", ("16",), ()),
    ("Deniz motoru (ton)", ("35",), ()),
    ("Kamyon", ("5",), ()),
    ("Hasan Rıza Soyak", ("Soyak",), ()),
]


def normalize(text: str) -> str:
    """Sayı biçimi farklarını (13.100 / 13100 / 13 100) ortadan kaldırır."""
    return re.sub(r"[.\s]", "", text.lower())


def contains(haystack: str, value: str) -> bool:
    """Değeri tam olarak arar, başka bir sayının parçası olarak değil.

    Düz alt dizi araması yanıltıyor: özet '688.000' yazdığında içinde
    '88.000' geçtiği için hata doğru sanılıyordu.
    """
    normalized = normalize(value)
    pattern = rf"(?<!\d){re.escape(normalized)}(?!\d)"
    return re.search(pattern, haystack) is not None


def run(summary: str) -> tuple[int, int, list[str]]:
    haystack = normalize(summary)
    problems = []
    passed = 0

    for label, accepted, forbidden in CHECKS:
        found = any(contains(haystack, value) for value in accepted)
        wrong = [bad for bad in forbidden if contains(haystack, bad)]

        if found and not wrong:
            passed += 1
        elif wrong:
            problems.append(f"  ✗ {label}: yanlış değer var {wrong} (doğrusu {accepted[0]})")
        else:
            problems.append(f"  ✗ {label}: '{accepted[0]}' özette yok")

    return passed, len(CHECKS), problems


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    summary = Path(sys.argv[1]).read_text(encoding="utf-8")
    passed, total, problems = run(summary)

    print(f"Doğrulama: {passed}/{total} geçti")
    for problem in problems:
        print(problem)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
