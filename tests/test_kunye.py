"""Künye ayrıştırma testleri.

Model çıktısı serbest metin olduğu için ayrıştırıcının bozuk, eksik ve
beklenmedik biçimlere dayanması gerekiyor. Buradaki örnekler gerçek
model çıktılarından ve öngörülen sapmalardan derlendi.

Kullanım:
    .venv/bin/python tests/test_kunye.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.summarize import (  # noqa: E402
    Kunye,
    _merge_contained,
    _merge_similar,
    limit_sentences,
    looks_like_person,
    turkish_upper,
)


def test_satir_basina_bir_ad() -> None:
    """Beklenen biçim: her ad kendi satırında."""
    kunye = Kunye.from_raw(
        "ÖZET: Geyve'de asilere karşı harekat.\n"
        "YER:\n- GEYVE\n- ADAPAZARI\n"
        "ŞAHIS:\n- OSMAN EFENDİ, YÜZBAŞI\n"
        "KURUM:\n- HARBİYE NEZARETİ\n"
    )
    assert kunye.yer_adlari == ["GEYVE", "ADAPAZARI"]
    assert kunye.sahis_adlari == ["OSMAN EFENDİ, YÜZBAŞI"]
    assert kunye.kurum_adlari == ["HARBİYE NEZARETİ"]
    assert kunye.ozet.startswith("Geyve")


def test_unvan_addan_koparilmaz() -> None:
    """Kişi kaydının içindeki virgül adı bölmemeli.

    'OSMAN EFENDİ, YÜZBAŞI' tek kişidir. Virgülle bölseydik iki ayrı kayıt
    üretirdik; bu yüzden ayırıcı olarak satır sonu kullanılıyor.
    """
    kunye = Kunye.from_raw(
        "ŞAHIS:\n"
        "- OSMAN EFENDİ, YÜZBAŞI\n"
        "- TAHSİN BEY, YÜZBAŞI (YÜZ KIRK ÜÇÜNCÜ ALAY KUMANDANI)\n"
    )
    assert len(kunye.sahis_adlari) == 2, kunye.sahis_adlari
    assert kunye.sahis_adlari[0] == "OSMAN EFENDİ, YÜZBAŞI"
    assert "(YÜZ KIRK ÜÇÜNCÜ ALAY KUMANDANI)" in kunye.sahis_adlari[1]


def test_bos_isaretleri_elenir() -> None:
    for marker in ("yok", "-", "—", "Belirtilmemiş"):
        kunye = Kunye.from_raw(f"YER:\n- {marker}\n")
        assert kunye.yer_adlari == [], f"'{marker}' elenmedi"


def test_tekrarlar_elenir() -> None:
    """Sayfa sayfa çıkarımda aynı ad birden çok kez geliyor."""
    kunye = Kunye.from_raw("YER:\n- GEYVE\n- Geyve\n- GEYVE\n")
    assert kunye.yer_adlari == ["GEYVE"]


def test_madde_isaretsiz_satirlar() -> None:
    """Model '- ' koymayı unutabiliyor."""
    kunye = Kunye.from_raw("YER:\nGEYVE\nADAPAZARI\n")
    assert kunye.yer_adlari == ["GEYVE", "ADAPAZARI"]


def test_etiket_varyasyonlari() -> None:
    """Etiketler küçük harfle ya da 'ADLARI' ekiyle gelebiliyor."""
    kunye = Kunye.from_raw("özet: Konu.\nkişi adları:\n- ALİ BEY\nkurum:\n- NEZARET\n")
    assert kunye.ozet == "Konu."
    assert kunye.sahis_adlari == ["ALİ BEY"]
    assert kunye.kurum_adlari == ["NEZARET"]


def test_cok_satirli_ozet() -> None:
    """3-4 cümlelik özet satırlara bölünmüş gelebilir."""
    kunye = Kunye.from_raw("ÖZET: Birinci cümle.\nİkinci cümle.\nYER:\n- GEYVE\n")
    assert "Birinci cümle." in kunye.ozet
    assert "İkinci cümle." in kunye.ozet
    assert kunye.yer_adlari == ["GEYVE"]


def test_etiketsiz_cikti_kaybolmaz() -> None:
    """Model biçimi tamamen ıskalarsa metin özete düşmeli, boş kalmamalı."""
    raw = "Bu belge Geyve'deki harekat hakkındadır."
    assert Kunye.from_raw(raw).ozet == raw


def test_turkce_buyuk_harf() -> None:
    assert turkish_upper("istanbul") == "İSTANBUL"
    assert turkish_upper("ışık") == "IŞIK"


def test_komutta_ornek_ozel_ad_yok() -> None:
    """Komut metni somut özel ad içermemeli.

    Komutta örnek olarak gerçek adlar ("HARBİYE NEZARETİ", "YÜZ KIRK ÜÇÜNCÜ
    ALAY") kullanıldığında model bunları belgede geçmedikleri halde künyeye
    kopyaladı. Arşiv kaydına uydurma kurum adı girmek, alanı boş bırakmaktan
    çok daha kötü; bu yüzden komutta yalnızca tür adları geçebilir.
    """
    from core.summarize import ADLAR_INSTRUCTION, OZET_INSTRUCTION

    # İzin verilenler komutların kendi vurgu sözcükleri.
    izinli = {
        "İLK CÜMLE", "KISA CÜMLE", "HER ADI KENDİ SATIRINA",
        "BÜYÜK HARFLE", "ÖNEMLİ", "KULLANMA", "YAZILMAZ",
    }
    for ad, komut in (("ÖZET", OZET_INSTRUCTION), ("ADLAR", ADLAR_INSTRUCTION)):
        obekler = re.findall(r"\b[A-ZÇĞİÖŞÜ]{3,}(?:\s+[A-ZÇĞİÖŞÜ]{2,})+\b", komut)
        sizinti = [o for o in obekler if o not in izinli]
        assert not sizinti, f"{ad} komutunda özel ad var, modele sızabilir: {sizinti}"


def test_ozet_cumle_sinirlanir() -> None:
    """Model 'en fazla 4 cümle' kuralını tutmuyor, sınır kodda uygulanıyor."""
    uzun = (
        "Birinci cümle. İkinci cümle. Üçüncü cümle. "
        "Dördüncü cümle. Beşinci cümle. Altıncı cümle."
    )
    sonuc = limit_sentences(uzun)
    assert sonuc.endswith("Dördüncü cümle."), sonuc
    assert "Beşinci" not in sonuc


def test_ozet_kelime_sinirlanir_ve_cumle_yarida_kesilmez() -> None:
    """Uzun anlatı katalog alanını doldurmamalı; cümle bütünü korunmalı."""
    metin = (
        "Belgenin asıl olayı açıklanmıştır. "
        "Bu ikinci cümlede katalog alanını gereksiz yere uzatan çok sayıda "
        "ayrıntı ve tekrar bulunmaktadır. "
        "Üçüncü cümle de uzun olduğu için özete alınmamalıdır."
    )
    sonuc = limit_sentences(metin, max_words=16)
    assert sonuc == "Belgenin asıl olayı açıklanmıştır.", sonuc
    assert len(sonuc.split()) <= 16


def test_sayidaki_nokta_cumle_sonu_sayilmaz() -> None:
    """'650.000' içindeki nokta özeti ortadan bölmemeli."""
    metin = "Çiftlikte 650.000 fidan ve 88.000 omca vardır. İkinci cümle burada."
    sonuc = limit_sentences(metin)
    assert "650.000" in sonuc
    assert "88.000" in sonuc
    assert "İkinci cümle burada." in sonuc


def test_kisa_ozet_dokunulmaz() -> None:
    metin = "Tek cümlelik özet."
    assert limit_sentences(metin) == metin
    assert limit_sentences("") == ""


def test_makam_kisi_listesinden_ayiklanir() -> None:
    """Model unvanları kişi adı olarak yazmayı sürdürüyor.

    1957 belgesinde 'Reisicumhur', 'Yugoslav Büyük Elçisi' ve 'Rumen
    Hükümeti Reisi' şahıs listesine düşmüştü. Bunlar makam, kişi değil.
    """
    kunye = Kunye.from_raw(
        "ŞAHIS:\n"
        "- Mareşal Tito\n"
        "- Reisicumhur\n"
        "- Mösyö Pesmazoğlu\n"
        "- Yugoslav Büyük Elçisi\n"
        "- Rumen Hükümeti Reisi\n"
    )
    assert kunye.sahis_adlari == ["Mareşal Tito", "Mösyö Pesmazoğlu"], kunye.sahis_adlari


def test_unvanli_kisi_adi_korunur() -> None:
    """Unvan adın yanındaysa kayıt kişiyi adlandırır, elenmemeli."""
    for entry in (
        "OSMAN EFENDİ, YÜZBAŞI",
        "HASAN RIZA SOYAK, RİYASETİCUMHUR UMUMÎ KÂTİBİ",
        "K. ATATÜRK",
        "Mareşal Tito",
    ):
        assert looks_like_person(entry), f"kişi adı elendi: {entry!r}"


def test_iyelik_yapisi_makam_sayilir() -> None:
    """'X'in Y'si' bir makam tarifidir, içinde özel ad geçse bile."""
    for entry in (
        "Yugoslavya'nın Ankara Büyük Elçisi",
        "Yugoslavya nın Ankara Büyük Elçisi",
        "Riyaseticumhur Umumî Kâtibi",
    ):
        assert not looks_like_person(entry), f"makam kişi sanıldı: {entry!r}"


def test_ayni_ad_iki_listede_kalmaz() -> None:
    """'Sovyet Rusya' hem yer hem kurum listesine düşmüştü.

    Bir ad yer olarak listelenmişse kurum sayılmıyor: yer tespiti belirgin
    şekilde daha güvenilir çıkıyor.
    """
    kunye = Kunye.from_raw(
        "YER:\n- BELGRAD\n- SOVYET RUSYA\n"
        "KURUM:\n- HARİCİYE NEZARETİ\n- SOVYET RUSYA\n"
    )
    assert "SOVYET RUSYA" in kunye.yer_adlari
    assert "SOVYET RUSYA" not in kunye.kurum_adlari
    assert "HARİCİYE NEZARETİ" in kunye.kurum_adlari


def test_yalniz_kurumda_gecen_ulke_yere_tasinir() -> None:
    kunye = Kunye.from_raw("YER:\n- ANKARA\nKURUM:\n- BULGARİSTAN\n- HARİCİYE NEZARETİ\n")
    assert "BULGARİSTAN" in kunye.yer_adlari
    assert "BULGARİSTAN" not in kunye.kurum_adlari


def test_ulke_sifatli_kurum_korunur() -> None:
    """'Bulgar Komünist Partisi' bir kuruluş, ülke değil."""
    kunye = Kunye.from_raw(
        "KURUM:\n- BULGAR KOMÜNİST PARTİSİ GENEL SEKRETERLİĞİ\n- BİRLEŞMİŞ MİLLETLER\n"
    )
    assert len(kunye.kurum_adlari) == 2, kunye.kurum_adlari


def test_kurum_yazim_farki_birlesir() -> None:
    """Koşular arası ek farkı aynı makamı iki kayda bölmemeli."""
    merged = _merge_similar(["Hariciye Nezaret", "Hariciye Nezareti", "Birleşmiş Milletler"])
    assert len(merged) == 2, merged
    assert "Hariciye Nezareti" in merged, "uzun biçim tutulmalı"


def test_sahis_unvanli_bicim_tercih_edilir() -> None:
    """Aynı kişi kimi koşuda yalnız adla, kimi koşuda unvanıyla geliyor."""
    merged = _merge_contained(
        ["Todojivko", "Bulgar Komünist Partisi Genel Sekreteri Todojivko", "Mareşal Tito"]
    )
    assert len(merged) == 2, merged
    assert any("Genel Sekreteri Todojivko" in name for name in merged)
    assert "Mareşal Tito" in merged


def test_ayri_kisiler_birlestirilmez() -> None:
    merged = _merge_contained(["Mareşal Tito", "Mösyö Pesmazoğlu"])
    assert len(merged) == 2


def test_ayri_kurumlar_birlestirilmez() -> None:
    merged = _merge_similar(["Hariciye Nezareti", "Dahiliye Nezareti"])
    assert len(merged) == 2, merged


def test_markdown_ciktisi() -> None:
    kunye = Kunye.from_raw("ÖZET: Konu.\nYER:\n- GEYVE\n")
    rendered = kunye.as_markdown()
    assert "Belge Özeti" in rendered
    assert "GEYVE" in rendered
    assert "_yok_" in rendered, "boş alanlar işaretlenmeli"


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
