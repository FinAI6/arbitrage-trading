import streamlit as st


# 페이지 설정
st.set_page_config(
    page_title="Arbitrage Trading",
    page_icon="💹",
    layout="wide"
)

if "alert_log" not in st.session_state:
    st.session_state.alert_log = {}
