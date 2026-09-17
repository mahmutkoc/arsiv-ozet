"""Sayfa notu üretiminin kararlılığını ölçer.

Künyenin son çağrısı aynı girdide %100 kararlı çıktı. Geriye tek aday
kalıyor: sayfa notları. Bütün boru hattını birkaç kez çalıştırmak yerine
birkaç sayfanın notunu tekrar tekrar üretip karşılaştırıyoruz — aynı
soruyu dakikalar yerine saniyelerde cevaplıyor.

Kullanım:
    .venv/bin/python tests/not_kararsizligi.py data/ornek --sayfa 3 --kez 3
"""

from __future__ import annotations

import argparse
import difflib
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pipeline import read_pages  # noqa: E402
from core.summarize import PAGE_NOTE_INSTRUCTION, PAGE_NOTE_TOKENS, LocalModel  # noqa: E402

# Belgedeki gerçek değerler aranıyor. Madde numaraları ("1.", "2.") sayı
# sayılmamalı: model kimi koşuda numaralı, kimi koşuda işaretli liste
# yazıyor ve bu, içerik oynuyormuş gibi görünmesine yol açıyordu.
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s")
NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def document_numbers(text: str) -> set[str]:
    """Metindeki gerçek sayıları, madde numaralarını atarak toplar."""
    without_markers = LIST_MARKER.sub("", text)
    return {n.rstrip(".,") for n in NUMBER.findall(without_markers)}


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.split(), b.split()).ratio()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sayfa notu kararlılığını ölçer.")
    parser.add_argument("kaynak", type=Path, nargs="?", default=Path("data/ornek"))
    parser.add_argument("--sayfa", type=int, default=3, help="Kaç sayfa denensin")
    parser.add_argument("--kez", type=int, default=3, help="Her sayfa kaç kez")
    args = parser.parse_args()

    pages = [p for p in read_pages(args.kaynak) if p.text.strip()][: args.sayfa]
    print(f"{len(pages)} sayfa, her biri {args.kez} kez\n")

    with LocalModel() as model:
        for page in pages:
            runs = []
            for index in range(args.kez):
                print(f"  sayfa {page.number}, koşu {index + 1}/{args.kez}…", flush=True)
                runs.append(
                    model.ask(
                        PAGE_NOTE_INSTRUCTION.format(number=page.number),
                        page.text,
                        max_tokens=PAGE_NOTE_TOKENS,
                    )
                )

            pairs = [
                similarity(runs[i], runs[j])
                for i in range(len(runs))
                for j in range(i + 1, len(runs))
            ]
            numbers = [document_numbers(r) for r in runs]
            common = set.intersection(*numbers)
            everything = set.union(*numbers)

            print(f"\n  SAYFA {page.number}")
            print(f"    metin benzerliği : {statistics.mean(pairs):.0%}")
            print(f"    kelime sayısı    : {[len(r.split()) for r in runs]}")
            print(f"    sayılar          : her koşuda {len(common)}/{len(everything)}")
            if everything - common:
                print(f"    oynayan sayılar  : {sorted(everything - common)}")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
