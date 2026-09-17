"""OCR çıktısındaki harf hatalarını dil modeliyle onarır.

Düşük çözünürlüklü taramada Tesseract kelimeleri harf harf tanıdığı için
bağlamdan bağımsız hata yapıyor: "hediye" → "iye", "Büyük" → "Büytik".
İnsan okuyucu bunları bağlamdan düzeltiyor; model de düzeltebilir.

Tehlike, modelin onarmak yerine yeniden yazması. Arşiv metninde dönem
imlası ("vucud", "mıntaka", "digeri") korunmalı ve hiçbir bilgi
eklenmemeli. Bu yüzden çıktı körü körüne kabul edilmiyor: değişen kelime
oranı ölçülüp eşiği aşarsa düzeltme reddedilip özgün metin korunuyor.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from core.summarize import LocalModel

# Model onarmak yerine yeniden yazmaya başlarsa bu oranlar taşar ve
# düzeltme tümden reddedilir. Sayılar temkinli seçildi: gerçek OCR
# onarımı sayfa başına birkaç kelimeyi etkiliyor.
MAX_CHANGED_RATIO = 0.15
MAX_LENGTH_DRIFT = 0.10

CORRECTION_PROMPT = """Aşağıdaki metin, eski bir daktilo belgesinin OCR
çıktısıdır. Tarayıcı bazı harfleri yanlış tanımış. Görevin YALNIZCA bu harf
hatalarını onarmak.

Kesin kurallar:
- Metni yeniden yazma. Cümleleri değiştirme, kısaltma, uzatma.
- Sadece Türkçede var olmayan, açıkça bozuk kelimeleri düzelt.
- Dönemin imlasına DOKUNMA. "vucud", "mıntaka", "digeri", "taktirde",
  "mevcud", "tetbir" gibi yazımlar doğrudur, bunları değiştirme.
- Hiçbir kelime ekleme, hiçbir kelime silme.
- Sayıları asla değiştirme.
- Bir kelimeden emin değilsen olduğu gibi bırak.
- Satır düzenini koru.
- Yalnızca düzeltilmiş metni yaz, açıklama ekleme.

METİN:
"""

# Nokta ve kesme işareti kelimenin içindeyse parçası sayılır: "88.000" tek
# sayı, "Atatürk'ün" tek kelime. Aksi halde bir sayının değişmesi iki ayrı
# değişiklik gibi görünüyor ve "88.000 → 688.000" gibi kritik bir sapma
# raporda "88 → 688" diye kayboluyordu.
WORD = re.compile(r"\w+(?:[.,'’]\w+)*", re.UNICODE)


@dataclass
class Correction:
    """Bir sayfanın onarım sonucu."""

    text: str
    changes: list[tuple[str, str]] = field(default_factory=list)
    rejected: bool = False
    reason: str = ""


def find_changes(before: str, after: str) -> list[tuple[str, str]]:
    """Değişen kelimeleri (eski, yeni) çiftleri olarak çıkarır."""
    old_words, new_words = WORD.findall(before), WORD.findall(after)
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)

    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            changes.append((" ".join(old_words[i1:i2]), " ".join(new_words[j1:j2])))
    return changes


def correct_page(model: LocalModel, text: str) -> Correction:
    """Bir sayfanın OCR hatalarını onarır.

    Model metni yeniden yazmaya kalkarsa düzeltme reddedilir; bozuk ama
    özgün metin, akıcı ama uydurulmuş metinden iyidir.
    """
    if not text.strip():
        return Correction(text=text)

    original_words = len(WORD.findall(text))
    # Onarılan metin girdiyle aynı uzunlukta olacağı için token bütçesi
    # cömert tutuluyor; kesilen çıktı metnin sonunu yutardı.
    proposed = model.ask(CORRECTION_PROMPT, text, max_tokens=int(original_words * 4) + 200)

    if not proposed.strip():
        return Correction(text=text, rejected=True, reason="model boş döndü")

    proposed_words = len(WORD.findall(proposed))
    if original_words:
        drift = abs(proposed_words - original_words) / original_words
        if drift > MAX_LENGTH_DRIFT:
            return Correction(
                text=text,
                rejected=True,
                reason=f"uzunluk %{drift:.0%} değişti, metin yeniden yazılmış olabilir",
            )

    changes = find_changes(text, proposed)
    changed_words = sum(len(WORD.findall(old)) for old, _ in changes)
    if original_words and changed_words / original_words > MAX_CHANGED_RATIO:
        return Correction(
            text=text,
            rejected=True,
            reason=f"kelimelerin %{changed_words / original_words:.0%}'i değişti",
        )

    return Correction(text=proposed.strip(), changes=changes)


def correct_pages(model: LocalModel, page_texts: list[str]) -> list[Correction]:
    return [correct_page(model, text) for text in page_texts]
