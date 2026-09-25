"""Asıl arşivi açmayan, yalnızca oturum sonuçlarını gösteren çevrimiçi demo."""
import streamlit as st

from core.demo import DemoQueue, PASSWORD_FILE, SAMPLE
from core.summarize import limit_sentences

st.set_page_config(page_title="Arşiv Künye · Demo", page_icon="📜", layout="wide")


@st.cache_resource
def get_queue():
    return DemoQueue()


def main():
    st.title("📜 Arşiv Künye · Demo")
    try:
        password = PASSWORD_FILE.read_text().strip()
    except OSError:
        password = ""
    if len(password) < 16:
        st.error("Demo giriş ayarları hazır değil.")
        st.stop()
    queue = get_queue()
    if not st.session_state.get("authenticated"):
        with st.form("login", clear_on_submit=True):
            entered = st.text_input("Demo şifresi", type="password")
            login = st.form_submit_button("Giriş yap")
        if login:
            if queue.authenticate(entered, password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Giriş yapılamadı. Şifreyi kontrol edin; çok deneme yaptıysanız bir dakika bekleyin.")
        st.stop()
    st.info("Arkadaşlar için deneme sürümü. Yalnızca paylaşılabilir örnek belgeler yükleyin. "
            "Dosyalar internet üzerinden paylaşım tüneli aracılığıyla sunucu bilgisayara gelir.")
    st.caption("Sonuçlar yalnızca bu oturumda gösterilir; arşive kaydedilmez. "
               "Geçici dosyalar okuma bitince silinir. Model çıktısını kontrol ederek kullanın.")
    if st.button("Çıkış yap"):
        job = st.session_state.get("job")
        if job:
            job.cancel()
        st.session_state.clear()
        st.rerun()
    job = st.session_state.get("job")
    busy = job is not None and not job.done()
    sample = st.checkbox("Dosya yüklemeden kurgusal örnek metni dene", disabled=busy)
    if sample:
        st.text(SAMPLE)
    uploaded = st.file_uploader(
        "Sayfaları okuma sırasıyla seçin: en fazla 15 sayfa, toplam 20 MB",
        type=["jpg", "jpeg", "png", "tif", "tiff", "pdf"],
        accept_multiple_files=True, disabled=busy or sample,
    )
    if st.button("Oku ve künye çıkar", type="primary", disabled=busy):
        if not sample and not uploaded:
            st.warning("Dosya seçin veya kurgusal örneği işaretleyin.")
        elif not sample and (len(uploaded) > 15 or sum(f.size for f in uploaded) > 20 * 1024 * 1024):
            st.error("En fazla 15 dosya ve toplam 20 MB yükleyebilirsiniz.")
        else:
            try:
                files = [] if sample else [(f.name, f.getvalue()) for f in uploaded]
                st.session_state.job = queue.submit(files, sample=sample)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    show_result()


@st.fragment(run_every="3s")
def show_result():
    job = st.session_state.get("job")
    if job is None:
        return
    if not job.done():
        st.info("Belgeniz işleniyor… Birkaç dakika sürebilir." if job.running()
                else "Belgeniz sırada; önceki işlem bitince başlayacak.")
        st.session_state.was_busy = True
        return
    if st.session_state.pop("was_busy", False):
        st.rerun()
    try:
        kunye, pages, words = job.result()
    except Exception:
        st.error("Belge işlenemedi. Dosyanın açılabildiğini, sayfa ve boyut sınırlarını kontrol edin. "
                 "Tekrar deneyin; sorun sürerse demo sahibine bildirin.")
        return
    st.success(f"{pages} sayfa, {words} kelime işlendi.")
    st.subheader("Belge özeti")
    st.code(limit_sentences(kunye.ozet), language=None, wrap_lines=True)
    for title, names in [("Madde ve yer adları", kunye.yer_adlari),
                         ("Şahıs adları", kunye.sahis_adlari),
                         ("Tüzel kuruluş adları", kunye.kurum_adlari)]:
        st.subheader(title)
        st.code("\n".join(names) or "Bulunamadı", language=None)


if __name__ == "__main__":
    main()
