"""Metin temizleme testleri.

Kullanım:
    .venv/bin/python tests/test_clean.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clean import (  # noqa: E402
    clean_page,
    dehyphenate,
    find_boilerplate,
    fix_known_misreads,
    hyphenation_candidates,
    is_noise,
    looks_like_stamp,
)

# Sözlük yerine geçen sabit tablo: testler macOS yazım denetleyicisine
# bağlı kalmasın, karar mantığı yalıtılmış olarak sınansın.
LEXICON = {
    "dahilinde": True,
    "telefon": True,
    "elektrik": True,
    "türkyunan": False,
    "çeşitleraâe": False,
    "demirbaşlarını": True,
}


def test_tireli_bolunme_birlesir() -> None:
    metin = "ticari esaslar dahilin-\nde idare edildikleri"
    assert dehyphenate(metin, LEXICON) == "ticari esaslar dahilinde idare edildikleri"


def test_gecersiz_birlesim_korunur() -> None:
    """İkinci parça bozuksa birleştirme çöp üretir; dokunulmamalı."""
    metin = "muhtelif yaşlarda ve çeşitler-\nâe 650.000 fidan"
    assert dehyphenate(metin, LEXICON) == metin


def test_mesru_tireli_birlesik_bozulmaz() -> None:
    """'Türk-Yunan' satır sonuna denk gelirse birleştirilmemeli."""
    metin = "Türk-\nYunan münasebetleri"
    assert dehyphenate(metin, LEXICON) == metin


def test_farkli_tire_isaretleri() -> None:
    """OCR tireyi kısa çizgi, uzun çizgi ya da benzeri okuyabiliyor."""
    for dash in ("-", "‐", "–", "—"):
        metin = f"dahilin{dash}\nde"
        assert dehyphenate(metin, LEXICON) == "dahilinde", f"{dash!r} tanınmadı"


def test_satir_ici_tire_bozulmaz() -> None:
    """Yalnızca satır sonundaki tire çözülür."""
    metin = "dahilin-de aynı satırda"
    assert dehyphenate(metin, LEXICON) == metin


def test_aday_tespiti() -> None:
    metin = "tele-\nfon tesisatı , elek-\ntrik tesisatı"
    assert hyphenation_candidates(metin) == [("tele", "fon"), ("elek", "trik")]


def test_yumusak_g_onarimi() -> None:
    assert fix_known_misreads("di#er") == "diğer"
    assert fix_known_misreads("geldi#i zaman") == "geldiği zaman"
    assert fix_known_misreads("No: #5") == "No: #5", "rakamdan önce dokunulmamalı"


def test_gurultu_tespiti() -> None:
    assert is_noise("EEE İİİ")
    assert is_noise("e a m ği m m m")
    assert is_noise("   ")
    assert not is_noise("Çifliklerin arazisi ile tesisat")


def test_antet_satiri_ocr_oynamasina_ragmen_elenir() -> None:
    """Aynı antet satırı her sayfada biraz farklı okunuyor.

    'Tesis Tarihi : 5 Mayıs 1925' bazı sayfalarda '5 Mays 195' çıkıyordu.
    Birebir imza karşılaştırması bu satırları tekrar saymadığı için antet
    metne sızıyordu; kümeleme bunu yakalamalı.
    """
    pages = [
        "Tesis Tarihi : 5 Mayıs 1925\nAnkarada Orman çifliği kurulmuştur",
        "Tesis Tarihi : 5 Mays 195\nYalovada Millet çifliği bulunmaktadır",
        "Tesis Tarihi : 5 Mayıs 1985\nSilifkede Tekir çifliği vardır",
        "Tesis Tarihi : 5 Mayıs 1925\nDörtyolda portakal bahçası mevcuttur",
    ]
    boilerplate = find_boilerplate(pages)
    cleaned = [clean_page(text, boilerplate) for text in pages]

    for text in cleaned:
        assert "Tesis Tarihi" not in text, f"antet satırı elenmedi: {text!r}"
    assert "Orman çifliği" in cleaned[0], "gövde metni de silinmiş"


def test_arsiv_damgasi_elenir() -> None:
    """Arşivin kendi damgası belgenin içeriği değil.

    Damga siyah mürekkepli olduğu için görüntüdeki kırmızı mühür temizliği
    yakalamıyor, OCR de her sayfada farklı bozuyor. 1957 belgesinde
    'Arşivler Genel Müdürlüğü' künyeye tüzel kuruluş olarak girmişti.
    """
    for line in (
        'biv-7 ARŞİVLERİ GENEL MüDür"dü',
        "CUMHURİYET ARŞİVİ",
        "” DE ARŞİVLERİ GEN",
        "Bevuzr ARŞİVLERİ GENEL MÜDÜR LCĞÜ",
    ):
        assert looks_like_stamp(line), f"damga tanınmadı: {line!r}"


def test_belge_anteti_damga_sanilmaz() -> None:
    """Belgenin kendi antedi ve gövdesi korunmalı."""
    for line in (
        "RİYASETİCUMHUR UMUMİ KÂTİPLİĞİ",
        "MÜLÂKAT PROSEVERBALİ",
        "Sayın Reisicumhurumuz, 15 Eylül 1957 Pazar günü",
        "BAŞVEKÂLETE.",
    ):
        assert not looks_like_stamp(line), f"içerik damga sanıldı: {line!r}"


def test_damga_yalnizca_sayfa_basinda_aranir() -> None:
    """Gövdede geçen meşru arşiv adı silinmemeli."""
    text = "\n".join(
        [
            "Birinci satır burada yer almaktadır",
            "İkinci satır burada yer almaktadır",
            "Üçüncü satır burada yer almaktadır",
            "Dördüncü satır burada yer almaktadır",
            "DEVLET ARŞİVLERİ GENEL MÜDÜRLÜĞÜ",
        ]
    )
    assert "DEVLET ARŞİVLERİ" in clean_page(text)


def test_govde_satirlari_tekrar_sayilmaz() -> None:
    """Yalnızca sayfaların çoğunda görünen satırlar elenmeli."""
    pages = [
        "Ankarada Orman çifliği kurulmuştur",
        "Yalovada Millet çifliği bulunmaktadır",
        "Silifkede Tekir çifliği vardır",
    ]
    boilerplate = find_boilerplate(pages)
    cleaned = [clean_page(text, boilerplate) for text in pages]
    assert all(text.strip() for text in cleaned), "gövde metni silindi"


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
