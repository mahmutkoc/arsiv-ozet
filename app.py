"""Arşiv künye çıkarıcı — Streamlit arayüzü.

Çalıştırmak için:
    .venv/bin/streamlit run app.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import streamlit as st

from core import store
from core.pipeline import extract, read_pages
from core.summarize import Kunye, LocalModel, find_model, limit_sentences

st.set_page_config(page_title="Arşiv Künye Çıkarıcı", page_icon="📜", layout="wide")


@st.cache_resource(show_spinner=False)
def get_model() -> LocalModel:
    """Modeli bir kez yükleyip açık tutar."""
    return LocalModel().__enter__()


# Veritabanı bağlantısı bilerek önbelleğe alınmıyor: sqlite3 bağlantıyı
# yalnızca onu açan iş parçacığında kullandırıyor, Streamlit ise her
# etkileşimi ayrı iş parçacığında çalıştırabiliyor. store.session() her
# iş için kısa ömürlü bir bağlantı açar.


def render_kunye(kunye: Kunye) -> None:
    """Künye alanlarını katalog formuna yapıştırılacak biçimde gösterir.

    Her alan st.code ile basılıyor: yerleşik kopyala düğmesi sayesinde tek
    tıkla panoya alınıp forma yapıştırılabiliyor. Adlar satır satır, çünkü
    formdaki liste kutusuna da her ad ayrı satır olarak giriliyor.
    """
    st.subheader("Katalog künyesi")
    st.caption("Her alanın sağ üstündeki simgeyle kopyalayıp forma yapıştır.")

    st.markdown("**Belge özeti**")
    summary = limit_sentences(kunye.ozet)
    st.code(summary or "(çıkarılamadı)", language=None, wrap_lines=True)
    if summary:
        st.caption(f"{len(summary.split())} kelime · Kısa katalog özeti")
    if summary != " ".join(kunye.ozet.split()):
        st.caption("Uzun özetin ilk tam cümleleri gösteriliyor; kayıt değiştirilmedi.")
        with st.expander("Kayıttaki özetin tamamı"):
            st.text(kunye.ozet)

    alanlar = [
        ("Madde ve yer adları", kunye.yer_adlari),
        ("Şahıs adları", kunye.sahis_adlari),
        ("Tüzel kuruluş adları", kunye.kurum_adlari),
    ]
    for baslik, adlar in alanlar:
        st.markdown(f"**{baslik}**")
        if adlar:
            st.code("\n".join(adlar), language=None)
        else:
            st.caption("Belgede bulunamadı")


def render_pages(pages: list[tuple[int, str]]) -> None:
    """(sayfa numarası, metin) çiftlerini açılır bir bölümde gösterir."""
    with st.expander(f"Sayfa metinleri ({len(pages)} sayfa)"):
        for number, text in pages:
            st.markdown(f"**Sayfa {number}**")
            st.text(text or "(boş)")


def page_process() -> None:
    st.header("Belge işle")

    uploaded = st.file_uploader(
        "Sayfa görüntülerini ya da PDF'i yükle",
        type=["jpg", "jpeg", "png", "tif", "tiff", "pdf"],
        accept_multiple_files=True,
        help="Katalogdan indirdiğin sayfaları sırayla seç. Tek bir PDF de olabilir.",
    )

    folder_input = st.text_input(
        "…ya da bir klasör yolu ver",
        placeholder="/Users/mahmut/arsiv-ozet/data/ornek",
    )

    name = st.text_input("Belge adı", placeholder="Orman Çiftliği'nin hazineye devri")

    if not st.button("Oku ve künye çıkar", type="primary"):
        return

    source: Path | None = None
    temp_dir: Path | None = None

    if uploaded:
        temp_dir = Path(tempfile.mkdtemp(prefix="arsiv-"))
        for index, item in enumerate(uploaded, start=1):
            # Yükleme sırası korunsun diye sıra numarasıyla yazıyoruz.
            (temp_dir / f"{index:03d}_{item.name}").write_bytes(item.getbuffer())
        pdfs = list(temp_dir.glob("*.pdf"))
        source = pdfs[0] if len(uploaded) == 1 and pdfs else temp_dir
    elif folder_input.strip():
        source = Path(folder_input.strip()).expanduser()
        if not source.exists():
            st.error(f"Bulunamadı: {source}")
            return
    else:
        st.warning("Dosya yükle ya da klasör yolu gir.")
        return

    progress = st.progress(0.0, text="Başlıyor…")

    def report(message: str, fraction: float) -> None:
        progress.progress(fraction, text=message)

    try:
        # Okuma önce yapılıyor: model 7 GB tuttuğu için OCR sırasında
        # bellekte olması görüntü okumayı başarısız kılabiliyor.
        pages = read_pages(source, on_progress=report)

        with st.spinner("Model hazırlanıyor…"):
            model = get_model()

        result = extract(source, pages, model=model, on_progress=report)
    except Exception as error:  # noqa: BLE001 - kullanıcıya sebebi göstermek istiyoruz
        progress.empty()
        st.error(f"İşlem başarısız: {error}")
        return
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    progress.empty()

    with store.session() as db:
        store.save(
            db,
            ad=name.strip() or result.name,
            kaynak=result.source,
            page_texts=[(p.number, p.source, p.text) for p in result.pages],
            ozet=result.kunye.ozet,
            adlar={
                "yer": result.kunye.yer_adlari,
                "sahis": result.kunye.sahis_adlari,
                "kurum": result.kunye.kurum_adlari,
            },
        )

    st.success(f"{result.page_count} sayfa, {result.word_count} kelime okundu.")
    render_kunye(result.kunye)
    if result.kunye.notes:
        with st.expander("Sayfa sayfa döküm"):
            for note in result.kunye.notes:
                st.text(note)
    render_pages([(p.number, p.text) for p in result.pages])


def page_archive() -> None:
    st.header("Kayıtlı belgeler")

    query = st.text_input("Ara", placeholder="çiftlik, hazine, 1937…")
    if query.strip():
        with store.session() as connection:
            rows = store.search(connection, query.strip())
        if not rows:
            st.info("Sonuç yok.")
        for row in rows:
            st.markdown(f"**{row['ad']}** — {row['sayfa_sayisi']} sayfa")
            st.caption(row["parca"])
            st.divider()
        return

    with store.session() as connection:
        documents = store.list_documents(connection)
        pages_by_document = {d.id: store.get_pages(connection, d.id) for d in documents}

    if not documents:
        st.info("Henüz belge yok. 'Belge işle' sekmesinden başla.")
        return

    for document in documents:
        with st.expander(f"{document.ad} — {document.sayfa_sayisi} sayfa · {document.olusturuldu}"):
            render_kunye(
                Kunye(
                    ozet=document.ozet or "",
                    yer_adlari=(document.yer_adlari or "").splitlines(),
                    sahis_adlari=(document.sahis_adlari or "").splitlines(),
                    kurum_adlari=(document.kurum_adlari or "").splitlines(),
                    notes=[],
                )
            )
            rows = pages_by_document[document.id]
            render_pages([(row["numara"], row["metin"]) for row in rows])


def main() -> None:
    st.title("📜 Arşiv Künye Çıkarıcı")
    st.caption("Tamamen yerel çalışır — belgeler hiçbir yere gönderilmez.")

    try:
        model_path = find_model()
        st.sidebar.success(f"Model: {model_path.name}")
    except RuntimeError as error:
        st.sidebar.error(str(error))

    tab_process, tab_archive = st.tabs(["Belge işle", "Kayıtlı belgeler"])
    with tab_process:
        page_process()
    with tab_archive:
        page_archive()


if __name__ == "__main__":
    main()
