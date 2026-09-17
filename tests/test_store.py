"""Depolama katmanı testleri.

Kullanım:
    .venv/bin/python tests/test_store.py
"""

from __future__ import annotations

import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import store  # noqa: E402

SAMPLE_PAGES = [(1, "a.jpg", "Orman çiftliği hazineye devredildi. 13.100 koyun mevcuttur.")]


def test_farkli_is_parcaciklarindan_kullanim(db_path: Path) -> None:
    """Bağlantı iş parçacıkları arasında paylaşılmamalı.

    Streamlit her etkileşimi ayrı bir iş parçacığında çalıştırdığı için
    bağlantıyı saklayıp yeniden kullanmak 'SQLite objects created in a
    thread can only be used in that same thread' hatası veriyordu.
    """

    def kaydet(index: int) -> int:
        with store.session(db_path) as connection:
            return store.save(
                connection,
                ad=f"Belge {index}",
                kaynak=f"/tmp/belge-{index}",
                page_texts=SAMPLE_PAGES,
                ozet=f"Özet {index}",
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(kaydet, range(4)))

    assert len(set(ids)) == 4, f"her kayıt ayrı kimlik almalı: {ids}"

    with store.session(db_path) as connection:
        assert len(store.list_documents(connection)) == 4


def test_ayni_kaynak_uzerine_yazilir(db_path: Path) -> None:
    """Aynı belge tekrar işlenirse çoğaltılmamalı."""
    for ozet in ("ilk", "ikinci"):
        with store.session(db_path) as connection:
            store.save(
                connection,
                ad="Belge",
                kaynak="/tmp/ayni",
                page_texts=SAMPLE_PAGES,
                ozet=ozet,
            )

    with store.session(db_path) as connection:
        documents = store.list_documents(connection)

    assert len(documents) == 1, f"tek kayıt bekleniyordu, {len(documents)} var"
    assert documents[0].ozet == "ikinci"


def test_turkce_arama(db_path: Path) -> None:
    """Ön ek ve ünsüz yumuşaması aramada karşılanmalı."""
    with store.session(db_path) as connection:
        store.save(
            connection,
            ad="Çiftlik belgesi",
            kaynak="/tmp/arama",
            page_texts=SAMPLE_PAGES,
            ozet="Hazineye devir",
        )

        for query in ("çiftlik", "çiftliği", "hazine", "koyun", "13.100"):
            assert store.search(connection, query), f"'{query}' bulunamadı"

        assert not store.search(connection, "kesinlikleyokbirkelime")
        assert not store.search(connection, "   ")


def main() -> int:
    tests = [
        test_farkli_is_parcaciklarindan_kullanim,
        test_ayni_kaynak_uzerine_yazilir,
        test_turkce_arama,
    ]

    failures = 0
    for test in tests:
        with tempfile.TemporaryDirectory() as folder:
            try:
                test(Path(folder) / "test.db")
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
