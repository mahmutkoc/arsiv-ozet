"""OCR onarımının güvenlik eşiği testleri.

Buradaki asıl mesele modelin ne kadar iyi düzelttiği değil — onu ancak
gerçek belgede ölçebiliriz. Test edilen şey, modelin metni yeniden
yazmaya kalktığında bunun yakalanıp reddedilmesi. Arşiv metninde bozuk
ama özgün metin, akıcı ama uydurulmuş metinden iyidir.

Kullanım:
    .venv/bin/python tests/test_correct.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.correct import correct_page, find_changes  # noqa: E402

ORIGINAL = (
    "tasarrufum altındaki bu çiflikleri , bütün tesisat , hayvanat ve "
    "demirbaşlarile beraber hazineye iye ediyorum . Çifliklerin arazisi "
    "ile tesisat ve demirbaşlarını mücmel olarak gösteren bir liste "
    "ilişiktir . Muktazi kanuni muamelenin yapılmasını dilerim ."
)


class FakeModel:
    """Sabit cevap döndüren model yerine geçer."""

    def __init__(self, reply: str) -> None:
        self.reply = reply

    def ask(self, instruction: str, text: str, **kwargs) -> str:
        return self.reply


def test_kucuk_onarim_kabul_edilir() -> None:
    """Birkaç kelimelik gerçek OCR onarımı geçmeli."""
    fixed = ORIGINAL.replace("hazineye iye", "hazineye hediye")
    result = correct_page(FakeModel(fixed), ORIGINAL)

    assert not result.rejected, result.reason
    assert "hediye ediyorum" in result.text
    assert result.changes == [("iye", "hediye")], result.changes


def test_yeniden_yazma_reddedilir() -> None:
    """Model metni kendi cümleleriyle yazarsa düzeltme atılmalı."""
    rewritten = (
        "Sahip olduğum çiftlikleri tüm tesisleri, hayvanları ve eşyalarıyla "
        "birlikte devlet hazinesine bağışlıyorum. Çiftliklerin arazileri ve "
        "eşyalarını özetleyen bir liste ektedir. Gerekli yasal işlemin "
        "yapılmasını rica ederim."
    )
    result = correct_page(FakeModel(rewritten), ORIGINAL)

    assert result.rejected, "yeniden yazma kabul edildi"
    assert result.text == ORIGINAL, "reddedilince özgün metin korunmalı"


def test_kisaltma_reddedilir() -> None:
    """Model metni özetlerse uzunluk sapmasından yakalanmalı."""
    result = correct_page(FakeModel("Çiftlikler hazineye devredilmiştir."), ORIGINAL)

    assert result.rejected, "kısaltma kabul edildi"
    assert result.text == ORIGINAL


def test_bos_cevap_reddedilir() -> None:
    result = correct_page(FakeModel("   "), ORIGINAL)
    assert result.rejected
    assert result.text == ORIGINAL


def test_bos_sayfa_dokunulmadan_gecer() -> None:
    result = correct_page(FakeModel("herhangi bir şey"), "   ")
    assert not result.rejected
    assert result.text == "   "


def test_donem_imlasi_bozulursa_gorunur() -> None:
    """İmla modernleştirmesi değişiklik listesinde görünmeli.

    Eşiği aşmadığı sürece reddedilmez; amaç bu tür değişikliklerin
    denetlenebilir olması. Modelin bunu yapmaması komutla isteniyor.
    """
    modernized = ORIGINAL.replace("çiflikleri", "çiftlikleri")
    result = correct_page(FakeModel(modernized), ORIGINAL)

    assert ("çiflikleri", "çiftlikleri") in result.changes


def test_degisiklik_tespiti_sayilari_gorur() -> None:
    changes = find_changes("mevcut 88.000 adet", "mevcut 688.000 adet")
    assert changes == [("88.000", "688.000")], changes


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
