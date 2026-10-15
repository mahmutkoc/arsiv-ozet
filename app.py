"""Arşiv künye çıkarıcı — Streamlit arayüzü.

Çalıştırmak için:
    .venv/bin/streamlit run app.py
"""

from __future__ import annotations

import shutil
import os
import threading
import tempfile
import secrets
from pathlib import Path

import streamlit as st

from core import store
from core.ui import setup_interface, sidebar_footer
from core.pipeline import extract, read_pages
from core.summarize import Kunye, LocalModel, find_model, limit_sentences

st.set_page_config(page_title="Arşiv Künye Çıkarıcı", page_icon="📜", layout="wide")

SHARED = os.environ.get("ARSIV_SHARED") == "1"


@st.cache_resource
def shared_resources():
    from core.demo import DemoQueue
    return DemoQueue(), threading.Lock()


@st.cache_resource
def job_manager():
    from core.jobs import JobManager
    return JobManager()


@st.fragment(run_every='2s')
def job_status(owner):
    manager = job_manager()
    job, busy = manager.snapshot(owner)
    if job:
        if job['status'] in ('running', 'cancelling', 'saving'):
            st.progress(job['fraction'], text=job['message'])
            if st.button('İşlemi iptal et', disabled=job['status'] != 'running'):
                manager.cancel_job(owner)
                st.rerun()
        elif job['status'] == 'done':
            st.success(job['message'])
            result = job['result']
            if result is not None:
                render_kunye(result.kunye)
                render_pages([(p.number, p.text) for p in result.pages])
        elif job['status'] == 'cancelled':
            st.info(job['message'])
        else:
            st.error(job['message'])
    if busy and (not job or job['status'] not in ('running', 'cancelling')):
        st.info('Başka bir belge işleniyor; tamamlanınca yeni işlem başlatabilirsiniz.')


def require_login():
    from core.demo import PASSWORD_FILE
    try:
        password = PASSWORD_FILE.read_text().strip()
    except OSError:
        password = ""
    if len(password) < 16:
        st.error("Paylaşım giriş ayarları hazır değil.")
        st.stop()
    if not st.session_state.get("archive_authenticated"):
        with st.form("archive_login", clear_on_submit=True):
            entered = st.text_input("Arşiv şifresi", type="password")
            login = st.form_submit_button("Giriş yap")
        if login and shared_resources()[0].authenticate(entered, password):
            st.session_state.archive_authenticated = True
            st.rerun()
        elif login:
            st.error("Giriş yapılamadı. Şifreyi kontrol edin veya bir dakika bekleyin.")
        st.stop()
    if st.sidebar.button("Çıkış yap"):
        st.session_state.clear()
        st.rerun()


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
    st.header("Belgelerden katalog künyesine.")
    st.caption("Gömlekteki sayfaları yükleyin, künye taslağını hazırlayın ve kontrol edin.")
    # Tahmin edilemez takip anahtarı yenilemede URL'de kalır; giriş kontrolü önce yapılır.
    owner = st.query_params.get('islem', '')
    if len(owner) != 64 or any(c not in '0123456789abcdef' for c in owner):
        owner = secrets.token_hex(32)
        st.query_params['islem'] = owner
    st.caption('Bu sayfayı yenileseniz de işlem sürer. İptal için aşağıdaki düğmeyi kullanın. İşlem takip bağlantısını paylaşmayın.')
    input_column, result_column = st.columns([1, 1], gap="large")
    input_card = input_column.container(border=True)
    result_card = result_column.container(border=True)
    with result_card:
        job_status(owner)
        if job_manager().snapshot(owner)[0] is None:
            st.info("Katalog künyesi burada görünecek. Başlamak için belgelerinizi yükleyin.")
    with input_card:
        st.subheader("01 · Belgeleri yükleyin")

    uploaded = input_card.file_uploader(
        "Sayfa görüntülerini ya da PDF'i yükle",
        type=["jpg", "jpeg", "png", "tif", "tiff", "pdf"],
        accept_multiple_files=True,
        help="Sayfaları sırayla seç: en fazla 100 sayfa ve toplam 200 MB. Tek PDF veya görüntüler.",
    )

    input_card.caption("En fazla 100 sayfa · Toplam 200 MB. İnternet tünelinde tek yükleme isteği 100 MB ile sınırlıdır; büyük PDF için bu Mac'te http://127.0.0.1:8503 kullanın.")
    folder_input = "" if SHARED else input_card.text_input(
        "…ya da bir klasör yolu ver",
        placeholder="/Users/mahmut/arsiv-ozet/data/ornek",
    )

    name = input_card.text_input("Belge adı", placeholder="Orman Çiftliği'nin hazineye devri")
    input_card.caption("Üretilen bilgileri kaynak belgelerle karşılaştırarak kontrol edin.")

    if not input_card.button("Oku ve künye çıkar", type="primary", use_container_width=True):
        return

    source: Path | None = None
    temp_dir: Path | None = None

    if uploaded:
        if SHARED:
            from core.demo import validate_files
            try:
                validate_files([(item.name, item.getvalue()) for item in uploaded])
            except Exception:
                st.error("En fazla 100 sayfa ve toplam 200 MB: tek PDF veya geçerli görüntüler yükleyin. Sayfa boyutu ve dosya biçimi sınırları da geçerlidir.")
                return
        temp_dir = Path(tempfile.mkdtemp(prefix="arsiv-"))
        for index, item in enumerate(uploaded, start=1):
            # Yükleme sırası korunsun diye sıra numarasıyla yazıyoruz.
            (temp_dir / f"{index:03d}{Path(item.name).suffix.lower()}").write_bytes(item.getbuffer())
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

    try:
        accepted = job_manager().submit(owner, source, temp_dir, name)
    except Exception:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        st.error('İşlem başlatılamadı.')
        return
    if not accepted:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        st.warning('Başka bir belge işleniyor. Kendi işleminizi iptal ettiyseniz iptalin tamamlanmasını bekleyin.')
        return
    st.rerun()


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
    setup_interface()
    if SHARED:
        require_login()
        st.caption("Belgeler paylaşım tüneli üzerinden sunucu bilgisayara gönderilir ve orada işlenir. "
                   "Yeni sonuçlar ortak arşive kaydedilir; giriş yapan herkes kayıtları görebilir.")
    else:
        st.caption("Tamamen yerel çalışır — belgeler hiçbir yere gönderilmez.")

    page = st.sidebar.radio("Çalışma alanı", ["Belge işle", "Kayıtlı belgeler"])
    sidebar_footer()
    try:
        model_path = find_model()
        st.sidebar.success(f"Model: {model_path.name}")
    except RuntimeError as error:
        st.sidebar.error(str(error))

    if page == "Belge işle":
        page_process()
    else:
        page_archive()


if __name__ == "__main__":
    main()
