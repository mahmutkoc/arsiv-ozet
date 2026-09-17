"""OCR çıktısındaki artıkları temizler.

Ayıklanan iki tür kir var:
  - Mühür, imza ve kenar notlarından kalan anlamsız harf yığınları
  - Her sayfada tekrarlayan matbu antet kalıntıları

Metnin kendisine dokunulmuyor: eski imla (vucud, mıntaka, digeri) arşiv
sadakati için olduğu gibi korunuyor.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence

from core.lexicon import check_words
from core.text import turkish_lower

# Bir satırın gürültü sayılması için ortalama kelime uzunluğu bu değerin
# altında olmalı; "EEE İİİ" veya "e a m ği m m" gibi diziler böyle yakalanıyor.
MIN_MEAN_WORD_LENGTH = 2.3
MIN_LETTER_RATIO = 0.5
BOILERPLATE_PAGE_FRACTION = 0.5

LETTERS = re.compile(r"[0-9A-Za-zÇĞİIÖŞÜçğıöşü]")

# İmza için satırın bu kadar baş harfi kullanılıyor.
SIGNATURE_LENGTH = 16
MIN_LETTERS_IN_LINE = 4


def is_noise(line: str) -> bool:
    """Satırın OCR artığı olup olmadığına karar verir."""
    stripped = line.strip()
    if not stripped:
        return True

    # Tek başına duran sayfa numaraları anlam taşımıyor.
    if re.fullmatch(r"[0-9IVXivx\s.,)\-]{1,6}", stripped):
        return True

    letters = LETTERS.findall(stripped)
    if len(letters) < MIN_LETTERS_IN_LINE:
        return True
    if len(letters) / len(stripped) < MIN_LETTER_RATIO:
        return True

    words = stripped.split()
    if len(words) >= 3:
        mean_length = sum(len(w) for w in words) / len(words)
        if mean_length < MIN_MEAN_WORD_LENGTH:
            return True

    # Tek harfin tekrarından ibaret kelimeler ("EEE İİİ") mühür ve çizgi
    # artığıdır. Ortalama uzunluk kuralı bunları kaçırıyor: harf sayısı
    # yeterli ama satır anlamsız.
    if len(words) >= 2:
        repeated = sum(1 for w in words if len(w) >= 2 and len(set(turkish_lower(w))) == 1)
        if repeated >= len(words) / 2:
            return True

    return False


def signature(line: str) -> str:
    """Satırın kimliğini üretir.

    Rakamlar atılıyor: OCR aynı antet satırındaki yılı her sayfada farklı
    okuyabiliyor (1925 / 195 / 1985) ve sayı imzanın içinde kalırsa aynı
    satır farklı kimlik alıyor.
    """
    letters_only = re.sub(r"[^a-zçğıöşü]", "", turkish_lower(line))
    return letters_only[:SIGNATURE_LENGTH]


# İki imzanın aynı satırdan geldiğini kabul etmek için gereken benzerlik.
# Birebir eşleşme yetersiz: OCR aynı satırdan sayfadan sayfaya biraz farklı
# harf dizisi üretiyor ("mayıs" / "mays"), bu da tekrarın gözden kaçmasına
# yol açıyordu.
SIGNATURE_SIMILARITY = 0.82


def _cluster(signatures: list[str]) -> list[list[str]]:
    """Birbirine yakın imzaları aynı kümede toplar."""
    clusters: list[list[str]] = []
    for candidate in signatures:
        for cluster in clusters:
            if difflib.SequenceMatcher(None, candidate, cluster[0]).ratio() >= SIGNATURE_SIMILARITY:
                cluster.append(candidate)
                break
        else:
            clusters.append([candidate])
    return clusters


def find_boilerplate(page_texts: Sequence[str]) -> set[str]:
    """Sayfaların çoğunda tekrarlayan satırların imzalarını bulur.

    Antetten sızan 'Tesis Tarihi : 5 Mayıs 1925' gibi satırlar her sayfada
    biraz farklı okunduğu için benzerliğe göre kümeleniyor; bir küme
    sayfaların yarısından fazlasında görünüyorsa tekrar sayılıyor.
    """
    if len(page_texts) < 3:
        return set()

    per_page = [
        {signature(line) for line in text.splitlines() if line.strip()} - {""}
        for text in page_texts
    ]

    all_signatures = sorted({s for page in per_page for s in page})
    threshold = len(page_texts) * BOILERPLATE_PAGE_FRACTION

    boilerplate: set[str] = set()
    for cluster in _cluster(all_signatures):
        members = set(cluster)
        pages_seen = sum(1 for page in per_page if page & members)
        if pages_seen >= threshold:
            boilerplate |= members
    return boilerplate


# Tesseract yumuşak g'yi zaman zaman '#' okuyor ("di#er", "geldi#i").
# '#' bu evrakta hiç geçmediği için harf arasında görüldüğünde güvenle
# düzeltilebiliyor. Yalnızca harfle çevrili olanlar değişiyor; tek başına
# duran bir işaret varsa dokunulmuyor.
SOFT_G_MISREAD = re.compile(r"(?<=[a-zçğıöşüA-ZÇĞİÖŞÜ])#(?=[a-zçğıöşüA-ZÇĞİÖŞÜ])")


def fix_known_misreads(text: str) -> str:
    """Sistematik OCR ikamelerini düzeltir."""
    return SOFT_G_MISREAD.sub("ğ", text)


# Arşivin kendi damgası her sayfaya basılı ve belgenin içeriği değil.
# Siyah mürekkepli olduğu için görüntü aşamasındaki kırmızı mühür temizliği
# bunu yakalamıyor; OCR de her sayfada farklı bozuyor ("ARŞİVLERİ GENEL
# MüDür'dü", "DE ARŞİVLERİ GEN"), dolayısıyla tekrar tespiti de kümeleyemiyor.
# Bilinen ibarelere benzerlikten yakalıyoruz.
STAMP_PHRASES = (
    "devletarşivlerigenelmüdürlüğü",
    "başbakanlıkcumhuriyetarşivi",
    "cumhuriyetarşivi",
    "cumhurbaşkanlığıdevletarşivleribaşkanlığı",
)
STAMP_SIMILARITY = 0.55

# Damga sayfanın üstünde yer alıyor. Bu sınır, gövdede geçen meşru bir
# arşiv adının silinmesini önlüyor.
STAMP_SEARCH_LINES = 4


def looks_like_stamp(line: str) -> bool:
    """Satır arşiv damgasının bozuk okunmuş hali mi?"""
    letters = re.sub(r"[^a-zçğıöşü]", "", turkish_lower(line))
    if len(letters) < 8:
        return False
    return any(
        difflib.SequenceMatcher(None, letters, phrase).ratio() >= STAMP_SIMILARITY
        for phrase in STAMP_PHRASES
    )


def clean_page(text: str, boilerplate: set[str] = frozenset()) -> str:
    """Tek bir sayfayı temizler."""
    kept = []
    content_seen = 0
    for line in text.splitlines():
        if is_noise(line) or signature(line) in boilerplate:
            continue
        content_seen += 1
        if content_seen <= STAMP_SEARCH_LINES and looks_like_stamp(line):
            continue
        kept.append(fix_known_misreads(line.strip()))
    return "\n".join(kept)


# Daktilocu satır sonunda kelimeyi tireyle bölmüş: "tele-\nfon". OCR bunu
# doğru okuyor ama kelime iki parça halinde kalıyor; hem arama hem künye
# çıkarımı bundan zarar görüyor. Tire farklı işaretlerle okunabildiği için
# hepsi kabul ediliyor.
HYPHEN_BREAK = re.compile(
    r"([a-zçğıöşüA-ZÇĞİÖŞÜâîû]+)[-\u2010\u2011\u2013\u2014]\s*\n\s*([a-zçğıöşüA-ZÇĞİÖŞÜâîû]+)"
)


def hyphenation_candidates(text: str) -> list[tuple[str, str]]:
    """Satır sonunda tireyle bölünmüş kelime parçalarını bulur."""
    return [(m.group(1), m.group(2)) for m in HYPHEN_BREAK.finditer(text)]


def dehyphenate(text: str, valid: dict[str, bool]) -> str:
    """Satır sonunda tireyle bölünmüş kelimeleri birleştirir.

    Yalnızca birleşimi sözlükte olanlar birleşiyor. Böylece "Türk-Yunan"
    gibi meşru tireli birleşikler satır sonuna denk gelse bile bozulmuyor:
    "TürkYunan" sözlükte yok, olduğu gibi kalıyor.
    """

    def birlestir(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        if valid.get(turkish_lower(left + right)):
            return left + right
        return match.group(0)

    return HYPHEN_BREAK.sub(birlestir, text)


def clean_pages(page_texts: Sequence[str]) -> list[str]:
    """Sayfa grubunu, aralarındaki tekrarları da hesaba katarak temizler."""
    boilerplate = find_boilerplate(page_texts)
    cleaned = [clean_page(text, boilerplate) for text in page_texts]

    # Sözlük tek seferde sorgulanıyor: kelime başına süreç açmak çok yavaş.
    candidates = [pair for text in cleaned for pair in hyphenation_candidates(text)]
    if not candidates:
        return cleaned

    valid = check_words(sorted({turkish_lower(left + right) for left, right in candidates}))
    if not valid:  # Sözlük yoksa hiçbir şey birleştirilmiyor.
        return cleaned

    return [dehyphenate(text, valid) for text in cleaned]
