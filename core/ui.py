"""Arşiv arayüzünün görsel katmanı; belge işleme mantığından bağımsızdır."""
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]


def setup_interface() -> None:
    st.markdown(f"<style>{(ROOT / 'ui.css').read_text()}</style>", unsafe_allow_html=True)
    with st.sidebar:
        st.image(str(ROOT / 'tasarim-ornekleri' / 'kurum-logo.png'), width=100)
        st.markdown("## Arşiv Künye Çıkarıcı")
        st.caption("Belgeden katalog bilgisine")
        st.divider()
    st.caption("BELGE İŞLEME VE KATALOGLAMA · Mahmut Koç")


def sidebar_footer() -> None:
    with st.sidebar:
        st.divider()
        st.caption("Künye taslaklarını kaynak belgelerle karşılaştırarak kontrol edin.")
        st.caption("Bağımsız proje · Resmî kurum hizmeti değildir.")
