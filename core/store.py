"""Okunan belgeleri ve özetlerini SQLite'ta saklar.

Aynı belgeyi ikinci kez işlemeye gerek kalmaması ve geçmiş özetlerin
aranabilmesi için tutuluyor. Tam metin araması FTS5 ile yapılıyor.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data/arsiv.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS belge (
    id          INTEGER PRIMARY KEY,
    ad          TEXT NOT NULL,
    kaynak      TEXT NOT NULL UNIQUE,
    fon         TEXT,
    kutu        TEXT,
    gomlek      TEXT,
    tarih       TEXT,
    sayfa_sayisi INTEGER NOT NULL,
    ozet        TEXT,
    yer_adlari   TEXT,
    sahis_adlari TEXT,
    kurum_adlari TEXT,
    olusturuldu TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sayfa (
    id        INTEGER PRIMARY KEY,
    belge_id  INTEGER NOT NULL REFERENCES belge(id) ON DELETE CASCADE,
    numara    INTEGER NOT NULL,
    kaynak    TEXT NOT NULL,
    metin     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS sayfa_belge ON sayfa(belge_id);

CREATE VIRTUAL TABLE IF NOT EXISTS arama USING fts5(
    ad, ozet, metin, belge_id UNINDEXED, tokenize='unicode61'
);
"""


@dataclass
class Document:
    """Kaydedilmiş bir belge."""

    id: int
    ad: str
    kaynak: str
    sayfa_sayisi: int
    ozet: str | None
    yer_adlari: str | None
    sahis_adlari: str | None
    kurum_adlari: str | None
    olusturuldu: str


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Yeni bir bağlantı açar; şema yoksa oluşturur."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    _migrate(connection)
    return connection


# Künye alanları sonradan eklendi; CREATE TABLE IF NOT EXISTS eski
# veritabanlarına yeni sütun eklemediği için elle tamamlıyoruz.
ADDED_COLUMNS = {
    "yer_adlari": "TEXT",
    "sahis_adlari": "TEXT",
    "kurum_adlari": "TEXT",
}


def _migrate(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(belge)")}
    for column, column_type in ADDED_COLUMNS.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE belge ADD COLUMN {column} {column_type}")
    connection.commit()


@contextmanager
def session(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Kullanım süresince açık kalan, sonunda kapanan bağlantı.

    Bağlantıyı saklayıp yeniden kullanmak yerine her iş için yenisini
    açıyoruz: sqlite3 bir bağlantının yalnızca onu açan iş parçacığında
    kullanılmasına izin veriyor, Streamlit ise her etkileşimi ayrı bir
    iş parçacığında çalıştırabiliyor. Bağlantı açmak ucuz olduğu için
    bu, iş parçacığı korumasını devre dışı bırakmaktan daha güvenli.
    """
    connection = connect(path)
    try:
        yield connection
    finally:
        connection.close()


def save(
    connection: sqlite3.Connection,
    *,
    ad: str,
    kaynak: str,
    page_texts: Sequence[tuple[int, str, str]],
    ozet: str | None,
    adlar: dict[str, list[str]] | None = None,
    kunye: dict[str, str] | None = None,
) -> int:
    """Belgeyi kaydeder; aynı kaynak tekrar gelirse üzerine yazar."""
    kunye = kunye or {}
    adlar = adlar or {}

    def birlestir(key: str) -> str | None:
        # Adlar satır satır saklanıyor; form alanlarına da bu şekilde
        # yapıştırılıyor, ayrıca aramada bütün adlar tek metinde geçiyor.
        values = adlar.get(key) or []
        return "\n".join(values) if values else None

    with connection:
        connection.execute("DELETE FROM belge WHERE kaynak = ?", (kaynak,))
        cursor = connection.execute(
            """INSERT INTO belge (ad, kaynak, fon, kutu, gomlek, tarih,
                                  sayfa_sayisi, ozet, yer_adlari,
                                  sahis_adlari, kurum_adlari, olusturuldu)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ad,
                kaynak,
                kunye.get("fon"),
                kunye.get("kutu"),
                kunye.get("gomlek"),
                kunye.get("tarih"),
                len(page_texts),
                ozet,
                birlestir("yer"),
                birlestir("sahis"),
                birlestir("kurum"),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        belge_id = int(cursor.lastrowid)

        connection.executemany(
            "INSERT INTO sayfa (belge_id, numara, kaynak, metin) VALUES (?, ?, ?, ?)",
            [(belge_id, n, src, text) for n, src, text in page_texts],
        )

        connection.execute("DELETE FROM arama WHERE belge_id = ?", (belge_id,))
        connection.execute(
            "INSERT INTO arama (ad, ozet, metin, belge_id) VALUES (?, ?, ?, ?)",
            (
                ad,
                "\n".join(filter(None, [ozet, birlestir("yer"), birlestir("sahis"), birlestir("kurum")])),
                "\n".join(t for _, _, t in page_texts),
                belge_id,
            ),
        )
    return belge_id


def list_documents(connection: sqlite3.Connection) -> list[Document]:
    rows = connection.execute(
        """SELECT id, ad, kaynak, sayfa_sayisi, ozet, yer_adlari,
                  sahis_adlari, kurum_adlari, olusturuldu
           FROM belge ORDER BY olusturuldu DESC"""
    ).fetchall()
    return [Document(**dict(row)) for row in rows]


def get_pages(connection: sqlite3.Connection, belge_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT numara, kaynak, metin FROM sayfa WHERE belge_id = ? ORDER BY numara",
        (belge_id,),
    ).fetchall()


# Türkçede sözcük sonundaki sert ünsüz, ek alınca yumuşar:
# çiftlik → çiftliği, kitap → kitabı, ağaç → ağacı, mevcut → mevcudu.
# Ön ek araması bu değişimi kendiliğinden yakalayamadığı için her iki
# biçimi de sorguya koyuyoruz.
CONSONANT_SOFTENING = {"k": ("ğ", "g"), "p": ("b",), "ç": ("c",), "t": ("d",)}


def word_variants(word: str) -> list[str]:
    """Kelimenin arama sırasında denenecek biçimlerini üretir."""
    variants = [word]
    softened = CONSONANT_SOFTENING.get(word[-1:].lower())
    if softened:
        variants.extend(word[:-1] + letter for letter in softened)
    return variants


def to_fts_query(query: str) -> str:
    """Kullanıcı aramasını FTS5 sorgusuna çevirir.

    Türkçe sondan eklemeli olduğu için her kelimeye ön ek jokeri ekliyoruz:
    'hazine' araması 'hazineye'yi de bulsun. Kelimeler tırnağa alınarak
    FTS5'in operatör karakterleri etkisizleşiyor.
    """
    words = re.findall(r"\w+", query, flags=re.UNICODE)
    if not words:
        return ""

    clauses = []
    for word in words:
        alternatives = " OR ".join(f'"{v}"*' for v in word_variants(word))
        clauses.append(f"({alternatives})")
    return " AND ".join(clauses)


def search(connection: sqlite3.Connection, query: str, limit: int = 50) -> list[sqlite3.Row]:
    """Belge adı, özet ve tam metinde arama yapar."""
    fts_query = to_fts_query(query)
    if not fts_query:
        return []

    return connection.execute(
        """SELECT b.id, b.ad, b.sayfa_sayisi, b.ozet,
                  snippet(arama, 2, '[', ']', ' … ', 12) AS parca
           FROM arama JOIN belge b ON b.id = arama.belge_id
           WHERE arama MATCH ? ORDER BY rank LIMIT ?""",
        (fts_query, limit),
    ).fetchall()
