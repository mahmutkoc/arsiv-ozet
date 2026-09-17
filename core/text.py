"""Türkçe metin işlemleri.

Python'un yerleşik büyük/küçük harf dönüşümleri Türkçede yanlış sonuç
veriyor:

    'İ'.lower()  →  'i' + birleşen nokta (görünüşte 'i', eşleşmede değil)
    'I'.lower()  →  'i'   (olması gereken 'ı')
    'i'.upper()  →  'I'   (olması gereken 'İ')

Bu, karşılaştırmalarda sessiz hatalara yol açıyor: 'BULGARİSTAN' ülke
listesinde bulunamıyor, 'İİİ' tekrarlanan harf sayılmıyordu. Bütün
karşılaştırmalar buradaki işlevlerden geçmeli.
"""

from __future__ import annotations

# Şapkalı harfler dönem imlasında yaygın ("kâtib", "âmil"). Karşılaştırma
# sırasında düzleştiriliyor ki "kâtib" ile "katib" eşleşsin.
CIRCUMFLEX = str.maketrans("âîûÂÎÛ", "aiuAİU")


def turkish_lower(text: str) -> str:
    """Türkçe küçük harfe çevirir ('İ' → 'i', 'I' → 'ı')."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def turkish_upper(text: str) -> str:
    """Türkçe büyük harfe çevirir ('i' → 'İ', 'ı' → 'I')."""
    return text.replace("i", "İ").replace("ı", "I").upper()


def fold(text: str) -> str:
    """Karşılaştırma anahtarı: küçük harf, şapkasız, tek boşluk."""
    return " ".join(turkish_lower(text.translate(CIRCUMFLEX)).split())
