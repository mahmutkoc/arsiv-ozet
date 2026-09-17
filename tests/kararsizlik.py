"""Aynı girdide künye çıktısının koşudan koşuya ne kadar değiştiğini ölçer.

Bu oturumda defalarca iki koşu arasındaki farkı yaptığım değişikliğe
bağladım, oysa farkın ne kadarının gürültü olduğunu bilmiyordum. Bir
değişikliğin işe yarayıp yaramadığını söyleyebilmek için önce gürültü
seviyesini bilmek gerekiyor.

Sayfa notları bir kez üretilip yeniden kullanılıyor: en pahalı adım o ve
ölçmek istediğimiz şey son künye çağrısının kararlılığı.

Kullanım:
    .venv/bin/python tests/kararsizlik.py data/ornek --kez 3
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pipeline import read_pages  # noqa: E402
from core.summarize import (  # noqa: E402
    REDUCE_BATCH_WORD_LIMIT,
    SINGLE_PASS_WORD_LIMIT,
    Kunye,
    LocalModel,
    _condense,
    build_notes,
    kunye_from_text,
)


def jaccard(a: set[str], b: set[str]) -> float:
    """İki liste ne kadar örtüşüyor: 1.0 aynı, 0.0 hiç ortak yok."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def field_report(name: str, runs: list[list[str]]) -> None:
    sizes = [len(r) for r in runs]
    sets = [{item.casefold() for item in r} for r in runs]

    pairs = [
        jaccard(sets[i], sets[j])
        for i in range(len(sets))
        for j in range(i + 1, len(sets))
    ]
    overlap = statistics.mean(pairs) if pairs else 1.0

    common = set.intersection(*sets) if sets else set()
    everything = set.union(*sets) if sets else set()
    unstable = everything - common

    print(f"\n{name}")
    print(f"  koşu başına ad sayısı : {sizes}")
    print(f"  ortalama örtüşme      : {overlap:.0%}")
    print(f"  her koşuda çıkan      : {len(common)}/{len(everything)}")
    if unstable:
        print(f"  oynayanlar            : {sorted(unstable)[:8]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Künye çıktısının kararlılığını ölçer.")
    parser.add_argument("kaynak", type=Path, nargs="?", default=Path("data/ornek"))
    parser.add_argument("--kez", type=int, default=3)
    parser.add_argument(
        "--tam",
        action="store_true",
        help="Sayfa notlarını da her koşuda yeniden üret (yavaş ama gerçek oynaklık)",
    )
    args = parser.parse_args()

    print(f"Sayfalar okunuyor: {args.kaynak}")
    pages = read_pages(args.kaynak)
    texts = [p.text for p in pages]

    def kaynak_metin(model: LocalModel) -> tuple[str, list[str]]:
        """Künye çağrısına verilecek metni üretir."""
        if sum(len(t.split()) for t in texts if t.strip()) <= SINGLE_PASS_WORD_LIMIT:
            return "\n\n".join(texts), []

        notes = build_notes(model, texts)
        reducible = notes
        while (
            len(" ".join(reducible).split()) > REDUCE_BATCH_WORD_LIMIT
            and len(reducible) > 1
        ):
            reducible = _condense(model, reducible)
        return "\n\n".join(reducible), notes

    with LocalModel() as model:
        # Varsayılan kip notları sabit tutup yalnızca son çağrıyı ölçer.
        # --tam ise notları da her koşuda yeniden üretir; oynaklığın asıl
        # kaynağı orası olduğu için gerçek tabloyu bu veriyor.
        source, notes = ("", []) if args.tam else kaynak_metin(model)

        results: list[Kunye] = []
        for index in range(args.kez):
            print(f"Künye çıkarılıyor {index + 1}/{args.kez}…")
            if args.tam:
                source, notes = kaynak_metin(model)
            results.append(kunye_from_text(model, source, notes=notes))

    print("\n" + "=" * 64)
    field_report("YER ADLARI", [k.yer_adlari for k in results])
    field_report("ŞAHIS ADLARI", [k.sahis_adlari for k in results])
    field_report("KURUM ADLARI", [k.kurum_adlari for k in results])

    print("\nÖZETLER")
    for index, kunye in enumerate(results, 1):
        words = len(kunye.ozet.split())
        sentences = kunye.ozet.count(".")
        print(f"\n  [{index}] {words} kelime, {sentences} cümle")
        print(f"      {kunye.ozet[:150]}…")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
