import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from datetime import timedelta


TELEGRAM_TOKEN = st.secrets["telegram"]["token"]
TELEGRAM_CHAT_ID = st.secrets["telegram"]["chat_id"]

# 페이지 설정
st.set_page_config(page_title="📊 Binance vs Bybit Spread Monitor", layout="wide")
st.title("💹 Binance vs Bybit 스프레드 모니터링")

# 사용자 설정
spread_threshold = st.sidebar.slider("🚨 스프레드 기준(%)", 0.0, 2.0, 0.1, 0.1)
volume_threshold = st.sidebar.slider("📊 거래량 기준 (USDT)", 0, 10_000_000, 500_000, step=100_000)
refresh_interval = st.sidebar.slider("⏱️ 갱신 주기 (초)", 1, 30, 5)

# 자동 새로고침은 실시간 탭에만 적용
tab_options = ["📈 스프레드 차트", "💰 실시간 가격 리스트",  "💵 Binance vs Bitget 가격 비교",    "💵 Bitget vs Bybit 가격 비교", "⏳ 과거 스프레드 분석", "📊 상위 스프레드 종목 추세"]
selected_tab = st.radio("탭 선택", tab_options, horizontal=True, index=1)

if selected_tab in ["📈 스프레드 차트", "💰 실시간 가격 리스트"]:
    st_autorefresh(interval=refresh_interval * 1000, key="refresh")



def send_telegram_alert(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
    except Exception as e:
        st.warning(f"⚠️ 텔레그램 전송 실패: {e}")


@st.cache_data(ttl=30)
def get_binance_futures_symbols():
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return set(
            item['symbol']
            for item in data.get('symbols', [])
            if item.get("contractType") == "PERPETUAL"
            and item.get("quoteAsset") == "USDT"
            and item.get("status") == "TRADING"
        )
    except Exception as e:
        st.error(f"❌ Binance 심볼 정보를 불러올 수 없습니다: {e}")
        return set()

@st.cache_data(ttl=30)
def get_binance_prices():
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return {item['symbol']: float(item['price']) for item in r.json()}
    except Exception as e:
        st.error(f"❌ Binance 가격 정보를 불러올 수 없습니다: {e}")
        return {}

@st.cache_data(ttl=30)
def get_bybit_prices():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get('result', {}).get('list', [])
        return {item['symbol']: float(item['lastPrice']) for item in data}, set(item['symbol'] for item in data)
    except Exception as e:
        st.error(f"❌ Bybit 가격 정보를 불러올 수 없습니다: {e}")
        return {}, set()

@st.cache_data(ttl=30)
def get_binance_24h_volume():
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return {item['symbol']: float(item['quoteVolume']) for item in r.json()}
    except Exception as e:
        st.error(f"❌ Binance 거래량 정보를 불러올 수 없습니다: {e}")
        return {}

@st.cache_data(ttl=30)
def get_binance_funding_rates():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return {item["symbol"]: float(item["lastFundingRate"]) * 100 for item in r.json()}
    except Exception as e:
        st.error(f"❌ Binance 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}

@st.cache_data(ttl=30)
def get_bybit_funding_rates():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("result", {}).get("list", [])
        return {
            item["symbol"]: float(item["fundingRate"]) * 100
            for item in data if item.get("fundingRate") not in (None, '', 'null')
        }
    except Exception as e:
        st.error(f"❌ Bybit 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}



@st.cache_data(ttl=30)
def get_bitget_prices():
    try:
        url = "https://api.bitget.com/api/mix/v1/market/tickers?productType=umcbl"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])

        prices = {}
        original_symbols = {}

        for item in data:
            raw_symbol = item.get("symbol", "")  # 예: BTCUSDT_UMCBL, ETHUSDT
            if not raw_symbol or "last" not in item:
                continue

            # 정규화: BTC-USDT → BTCUSDT, BTCUSDT_UMCBL → BTCUSDT
            normalized = raw_symbol.replace("-", "").split("_")[0]

            prices[normalized] = float(item["last"])
            original_symbols[normalized] = raw_symbol

        return prices, set(prices.keys()), original_symbols

    except Exception as e:
        st.error(f"❌ Bitget 가격 정보를 불러올 수 없습니다: {e}")
        return {}, set(), {}



@st.cache_data(ttl=30)
def get_bitget_funding_rates():
    try:
        url = "https://api.bitget.com/api/v2/mix/market/funding-rate?productType=umcbl"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        return {
            item["symbol"]: float(item["fundingRate"]) * 100
            for item in data if item.get("fundingRate")
        }
    except Exception as e:
        st.error(f"❌ Bitget 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}

if "alert_log" not in st.session_state:
    st.session_state.alert_log = {}

if "chart_data" not in st.session_state:
    st.session_state.chart_data = {}

now = datetime.now().strftime("%H:%M:%S")

binance_symbols = get_binance_futures_symbols()
binance_prices = get_binance_prices()
bybit_prices, bybit_symbols = get_bybit_prices()
binance_volumes = get_binance_24h_volume()
binance_funding = get_binance_funding_rates()
bybit_funding = get_bybit_funding_rates()
bitget_prices, bitget_symbols, bitget_symbol_map = get_bitget_prices()


common_symbols = [
    s for s in binance_symbols & bybit_symbols
    if s in binance_prices and s in bybit_prices and binance_volumes.get(s, 0) >= volume_threshold
]



spread_list = []
for symbol in common_symbols:
    b_price = binance_prices[symbol]
    y_price = bybit_prices[symbol]
    spread = abs(b_price - y_price)
    spread_pct = spread / min(b_price, y_price) * 100
    spread_list.append({
        "symbol": symbol,
        "binance": b_price,
        "bybit": y_price,
        "spread": spread,
        "spread_pct": round(spread_pct, 4),
        "volume": binance_volumes.get(symbol, 0),
        "binance_funding": binance_funding.get(symbol, 0.0),
        "bybit_funding": bybit_funding.get(symbol, 0.0)
    })




spread_list = sorted(spread_list, key=lambda x: x["spread_pct"], reverse=True)
top_spreads = spread_list[:12]
# 이 아래에 알림 조건 루프 삽입
for item in spread_list:
    symbol = item["symbol"]
    spread_pct = item["spread_pct"]
    binance_funding = item["binance_funding"]
    bybit_funding = item["bybit_funding"]
    funding_gap = abs(binance_funding - bybit_funding)
    now = datetime.now()

    # 스프레드 알림
    if spread_pct >= 0.5:
        last_sent = st.session_state.alert_log.get(f"{symbol}_spread")
        if not last_sent or now - last_sent >= timedelta(hours=1):
            msg = (
                f"🚨 <b>{symbol} - 스프레드 경고</b>\n"
                f"💹 스프레드: <b>{spread_pct:.4f}%</b>\n"
                f"💰 Binance: ${item['binance']:.2f} | Bybit: ${item['bybit']:.2f}"
            )
            send_telegram_alert(msg)
            st.session_state.alert_log[f"{symbol}_spread"] = now

    # 펀딩비 알림 (Binance 또는 Bybit 중 하나라도 크면)
    if binance_funding >= 0.5 or bybit_funding >= 0.5:
        last_sent = st.session_state.alert_log.get(f"{symbol}_funding")
        if not last_sent or now - last_sent >= timedelta(hours=1):
            msg = (
                f"📢 <b>{symbol} - 펀딩비 경고</b>\n"
                f"📊 Binance: {binance_funding:.4f}% | Bybit: {bybit_funding:.4f}%"
            )
            send_telegram_alert(msg)
            st.session_state.alert_log[f"{symbol}_funding"] = now

    # 펀딩비 갭 알림
    if funding_gap >= 0.3:
        last_sent = st.session_state.alert_log.get(f"{symbol}_gap")
        if not last_sent or now - last_sent >= timedelta(hours=1):
            msg = (
                f"⚠️ <b>{symbol} - 펀딩비 차이 경고</b>\n"
                f"📊 Binance: {binance_funding:.4f}% | Bybit: {bybit_funding:.4f}%\n"
                f"🔀 차이: <b>{funding_gap:.4f}%</b>"
            )
            send_telegram_alert(msg)
            st.session_state.alert_log[f"{symbol}_gap"] = now



@st.cache_data(ttl=300)
def get_binance_klines(symbol, minutes):
    try:
        end_time = int(datetime.utcnow().timestamp() * 1000)
        start_time = end_time - minutes * 60 * 1000
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&startTime={start_time}&endTime={end_time}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume", "close_time",
                                         "quote_asset_volume", "number_of_trades", "taker_buy_base_volume",
                                         "taker_buy_quote_volume", "ignore"])
        df["binance_price"] = df["close"].astype(float)
        df["index"] = range(len(df))
        return df[["index", "binance_price"]]
    except Exception as e:
        st.error(f"❌ Binance 과거 데이터 오류: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_bybit_klines(symbol, minutes):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit={minutes}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json().get("result", {}).get("list", [])
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["bybit_price"] = df["close"].astype(float)
        df["index"] = range(len(df))
        return df[["index", "bybit_price"]]
    except Exception as e:
        st.error(f"❌ Bybit 과거 데이터 오류: {e}")
        return pd.DataFrame()



if selected_tab == "📈 스프레드 차트":
    for i in range(0, len(top_spreads), 3):
        row = st.columns(3)
        for j in range(3):
            if i + j < len(top_spreads):
                data = top_spreads[i + j]
                symbol = data['symbol']
                binance_price = data['binance']
                bybit_price = data['bybit']
                spread = data['spread']
                spread_pct = data['spread_pct']

                if symbol not in st.session_state.chart_data:
                    st.session_state.chart_data[symbol] = pd.DataFrame(columns=["Time", "Spread (%)"])
                df = st.session_state.chart_data[symbol]
                df.loc[len(df)] = [now, spread_pct]
                if len(df) > 60:
                    df = df.iloc[-60:]
                st.session_state.chart_data[symbol] = df

                with row[j]:
                    st.markdown(f"### <span style='font-size:18px'>{symbol}</span>", unsafe_allow_html=True)
                    st.markdown(
                        f"<span style='font-size:14px'>"
                        f"Binance: ${binance_price:,.2f} <br>Bybit: ${bybit_price:,.2f}<br>"
                        f"차이: ${spread:,.2f}<br>차이율: {spread_pct:.4f}%"
                        f"</span>", unsafe_allow_html=True
                    )

                    fig = px.line(df, x="Time", y="Spread (%)")
                    spread_min = df["Spread (%)"].min()
                    spread_max = df["Spread (%)"].max()
                    y_min = max(0, spread_min - (spread_max - spread_min) * 0.2)
                    y_max = spread_max + (spread_max - spread_min) * 0.2
                    fig.update_layout(height=250, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
                    fig.update_yaxes(range=[y_min, y_max])
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{symbol}")

                    if spread_pct > spread_threshold:
                        st.error(f"🚨 {symbol} 스프레드 {spread_pct:.4f}% 초과!")

elif selected_tab == "💰 실시간 가격 리스트":
    st.markdown("### 💵 실시간 가격 비교 (Binance vs Bybit)")
    filtered = [item for item in spread_list if item['spread_pct'] >= spread_threshold]
    if not filtered:
        st.info("해당 기준 이상의 종목이 없습니다.")
    else:
        price_df = pd.DataFrame(filtered)[[
            "symbol", "binance", "bybit", "spread", "spread_pct", "volume",
            "binance_funding", "bybit_funding"
        ]]
        price_df.columns = [
            "심볼", "Binance 가격", "Bybit 가격", "가격 차이 ($)", "차이율 (%)",
            "거래량 (USDT)", "Binance 펀딩피 (%)", "Bybit 펀딩피 (%)"
        ]
        price_df["🚨 알림"] = price_df["차이율 (%)"].apply(lambda x: "🔔" if x > spread_threshold else "")

        formatted_df = price_df.sort_values("차이율 (%)", ascending=False).copy()
        formatted_df["Binance 가격"] = formatted_df["Binance 가격"].map("${:,.2f}".format)
        formatted_df["Bybit 가격"] = formatted_df["Bybit 가격"].map("${:,.2f}".format)
        formatted_df["가격 차이 ($)"] = formatted_df["가격 차이 ($)"].map("${:,.2f}".format)
        formatted_df["차이율 (%)"] = formatted_df["차이율 (%)"].map("{:.4f}%".format)
        formatted_df["거래량 (USDT)"] = formatted_df["거래량 (USDT)"].map("{:,}".format)
        formatted_df["Binance 펀딩피 (%)"] = formatted_df["Binance 펀딩피 (%)"].map("{:.4f}%".format)
        formatted_df["Bybit 펀딩피 (%)"] = formatted_df["Bybit 펀딩피 (%)"].map("{:.4f}%".format)

        st.write(formatted_df)


elif selected_tab == "💵 Binance vs Bitget 가격 비교":
    st.markdown("### ⚖️ Binance vs Bitget 가격 비교")
    common_symbols_bb = [
        s for s in binance_symbols & bitget_symbols
        if s in binance_prices and s in bitget_prices and binance_volumes.get(s, 0) >= volume_threshold
    ]

    data = []
    for symbol in common_symbols_bb:
        b_price = binance_prices[symbol]
        g_price = bitget_prices[symbol]

        # 0으로 나누기 방지
        if b_price == 0 or g_price == 0:
            continue

        spread = abs(b_price - g_price)
        spread_pct = spread / min(b_price, g_price) * 100

        data.append({
            "symbol": symbol,
            "Binance 가격": b_price,
            "Bitget 가격": g_price,
            "가격 차이 ($)": spread,
            "차이율 (%)": spread_pct,
            "거래량 (USDT)": binance_volumes.get(symbol, 0)
        })

    df = pd.DataFrame(data)
    df = df[df["차이율 (%)"] >= spread_threshold]

    if df.empty:
        st.info("해당 기준 이상의 종목이 없습니다.")
    else:
        df["🚨 알림"] = df["차이율 (%)"].apply(lambda x: "🔔" if x > spread_threshold else "")
        df = df.sort_values("차이율 (%)", ascending=False)
        df["Binance 가격"] = df["Binance 가격"].map("${:,.2f}".format)
        df["Bitget 가격"] = df["Bitget 가격"].map("${:,.2f}".format)
        df["가격 차이 ($)"] = df["가격 차이 ($)"].map("${:,.2f}".format)
        df["차이율 (%)"] = df["차이율 (%)"].map("{:.4f}%".format)
        df["거래량 (USDT)"] = df["거래량 (USDT)"].map("{:,}".format)
        st.write(df)


elif selected_tab == "💵 Bitget vs Bybit 가격 비교":
    st.markdown("### ⚖️ Bitget vs Bybit 가격 비교")

    # Bitget 데이터 로드
    bitget_prices, bitget_symbols, bitget_symbol_map = get_bitget_prices()
    bybit_prices, bybit_symbols = get_bybit_prices()

    # 공통 심볼 도출 (정규화된 기준)
    common_symbols_gy = [
        s for s in bitget_symbols & bybit_symbols
        if s in bitget_prices and s in bybit_prices
    ]

    st.info(f"🔄 공통 비교 가능 종목 수: {len(common_symbols_gy)}")

    data = []
    for symbol in common_symbols_gy:
        g_price = bitget_prices[symbol]
        y_price = bybit_prices[symbol]

        # 0으로 나누기 방지
        if g_price == 0 or y_price == 0:
            continue

        spread = abs(g_price - y_price)
        spread_pct = spread / min(g_price, y_price) * 100

        data.append({
            "symbol": symbol,
            "Bitget 가격": g_price,
            "Bybit 가격": y_price,
            "가격 차이 ($)": spread,
            "차이율 (%)": spread_pct
        })

    df = pd.DataFrame(data)

    if df.empty or "차이율 (%)" not in df.columns:
        st.warning("📭 비교 가능한 종목이 없습니다.")
    else:
        df = df[df["차이율 (%)"] >= spread_threshold]
        df["🚨 알림"] = df["차이율 (%)"].apply(lambda x: "🔔" if x > spread_threshold else "")
        df = df.sort_values("차이율 (%)", ascending=False)
        df["Bitget 가격"] = df["Bitget 가격"].map("${:,.2f}".format)
        df["Bybit 가격"] = df["Bybit 가격"].map("${:,.2f}".format)
        df["가격 차이 ($)"] = df["가격 차이 ($)"].map("${:,.2f}".format)
        df["차이율 (%)"] = df["차이율 (%)"].map("{:.4f}%".format)
        st.write(df)




elif selected_tab == "⏳ 과거 스프레드 분석":
    st.markdown("### ⏳ 과거 1분봉 스프레드 분석")
    selected_symbol = st.selectbox("심볼 선택", sorted(common_symbols))
    duration_hours = st.slider("조회 시간 (시간 단위)", 1, 6, 3)

    @st.cache_data(ttl=300)
    def get_binance_klines(symbol, minutes):
        try:
            end_time = int(datetime.utcnow().timestamp() * 1000)
            start_time = end_time - minutes * 60 * 1000
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&startTime={start_time}&endTime={end_time}"
            r = requests.get(url)
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume", "close_time",
                                             "quote_asset_volume", "number_of_trades", "taker_buy_base_volume",
                                             "taker_buy_quote_volume", "ignore"])
            df["binance_price"] = df["close"].astype(float)
            df["index"] = range(len(df))
            return df[["index", "binance_price"]]
        except Exception as e:
            st.error(f"❌ Binance 과거 데이터 오류: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=300)
    def get_bybit_klines(symbol, minutes):
        try:
            url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit={minutes}"
            r = requests.get(url)
            r.raise_for_status()
            data = r.json().get("result", {}).get("list", [])
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
            df["bybit_price"] = df["close"].astype(float)
            df["index"] = range(len(df))
            return df[["index", "bybit_price"]]
        except Exception as e:
            st.error(f"❌ Bybit 과거 데이터 오류: {e}")
            return pd.DataFrame()

    minutes = duration_hours * 60
    binance_df = get_binance_klines(selected_symbol, minutes)
    bybit_df = get_bybit_klines(selected_symbol, minutes)

    if not binance_df.empty and not bybit_df.empty:
        df = pd.merge(binance_df, bybit_df, on="index", how="inner")
        df["timestamp"] = pd.to_datetime(df.index, unit="m", origin=pd.Timestamp.now() - pd.Timedelta(minutes=len(df)))
        df["spread_pct"] = abs(df["binance_price"] - df["bybit_price"]) / df[["binance_price", "bybit_price"]].min(axis=1) * 100

        st.markdown(f"**{selected_symbol} - 과거 {duration_hours}시간 스프레드 (%)**")
        fig = px.line(df, x="timestamp", y="spread_pct", title="과거 스프레드 추이 (실제 시간 기준)")
        fig.update_layout(
            height=400,
            xaxis_title="시간",
            yaxis_title="스프레드 (%)",
            xaxis=dict(showgrid=True),
            yaxis=dict(showgrid=True),
            margin=dict(l=40, r=20, t=40, b=40)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("📉 데이터를 불러올 수 없습니다.")
elif selected_tab == "📊 상위 스프레드 종목 추세":
    st.markdown("### 🔍 스프레드 상위 10개 종목 - 과거 추이 분석 (1분봉 기준)")
    duration_hours = st.slider("조회 시간 (시간 단위)", 1, 6, 3, key="top_spread_duration")
    minutes = duration_hours * 60

    top_symbols = [item["symbol"] for item in top_spreads[:10]]

    for symbol in top_symbols:
        binance_df = get_binance_klines(symbol, minutes)
        bybit_df = get_bybit_klines(symbol, minutes)

        if not binance_df.empty and not bybit_df.empty:
            df = pd.merge(binance_df, bybit_df, on="index", how="inner")
            df["timestamp"] = pd.to_datetime(df.index, unit="m", origin=pd.Timestamp.now() - pd.Timedelta(minutes=len(df)))
            df["spread_pct"] = abs(df["binance_price"] - df["bybit_price"]) / df[["binance_price", "bybit_price"]].min(axis=1) * 100

            st.markdown(f"#### 📌 {symbol}")
            fig = px.line(df, x="timestamp", y="spread_pct", title=f"{symbol} - 스프레드 추이")
            fig.update_layout(
                height=350,
                xaxis_title="시간",
                yaxis_title="스프레드 (%)",
                xaxis=dict(showgrid=True),
                yaxis=dict(showgrid=True),
                margin=dict(l=40, r=20, t=40, b=40)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"⚠️ {symbol} - 데이터를 불러올 수 없습니다.")
