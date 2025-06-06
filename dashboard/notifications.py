import requests
import streamlit as st

TELEGRAM_TOKEN = st.secrets["telegram"]["token"]
TELEGRAM_CHAT_ID = st.secrets["telegram"]["chat_id"]


def send_telegram_alert(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=payload,
                                 headers={'Content-Type': 'application/json'})
        response.raise_for_status()
    except Exception as e:
        st.warning(f"⚠️ 텔레그램 전송 실패: {e}")
