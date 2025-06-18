import requests
import time
import csv
from datetime import datetime
import os
import ccxt
from dotenv import load_dotenv
import traceback
from collections import defaultdict, deque
from time import sleep

load_dotenv()

binance = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_SECRET'),
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})

bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_API_KEY'),
    'secret': os.getenv('BYBIT_SECRET'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',      # ⬅️ 핵심: future → swap
        'defaultSubType': 'linear', # (선택) USDT Perp를 기본으로
    }
})

spread_threshold = 0.4# 1.5
exit_percent = 0.4
spread_hold_count = 3  # 스프레드 지속 조건 횟수, Top 1 연속 횟수
TOP_SYMBOL_LIMIT = 300  # 거래량 상위 몇 개 종목만 사용할지 설정/ 전체종목개수 381개
MIN_VOLUME_USDT = 5_000_000  # ✅ 24시간 거래대금 최소 기준 (예: 1천만 USDT 이상)

recent_spread_history = defaultdict(lambda: deque(maxlen=spread_hold_count))
open_positions = {}
pending_orders = {}

top1_history = defaultdict(lambda: deque(maxlen=spread_hold_count))
exit_condition_history = defaultdict(lambda: deque(maxlen=spread_hold_count))

def convert_symbol(exchange, raw_symbol):
    try:
        # Bybit v5: 선물(USDT Perp)만 로드
        params = {'category': 'linear'} if exchange.id == 'bybit' else {}
        exchange.load_markets(params=params)

        formatted_input = raw_symbol.replace('/', '').replace(':', '').upper()

        for market in exchange.markets.values():
            # CCXT 고유 ID 기준 매칭
            fmt = market['id'].replace('/', '').replace(':', '').upper()
            if formatted_input == fmt:
                if exchange.id == 'bybit':
                    # ✅ 선물(perp) 마켓만 허용
                    if not market.get('linear', False):
                        continue
                return market['symbol']
    except Exception as e:
        print(f"❌ [{exchange.id}] convert_symbol 실패: {raw_symbol} → {e}")
    return None

def get_order_average_price(exchange, order_id, symbol, params=None):
    try:
        if exchange.id == 'bybit':
            if params is None:
                params = {}
            params['acknowledged'] = True

        order = exchange.fetch_order(order_id, symbol, params=params)
        return order.get('average')
    except Exception as e:
        print(f"❌ 평균가 조회 실패 ({exchange.id}): {e}")
        return None

def calculate_qty_for_fixed_usdt(exchange, symbol, price, target_usdt=100):
    market = exchange.market(symbol)
    qty = target_usdt / price
    amount_precision = market.get('precision', {}).get('amount')
    if amount_precision is None:
        amount_precision = 2  # 기본값 사용
    precision = int(amount_precision)

    return round(qty, precision)

def get_binance_futures_symbols(max_retries=3, delay=2):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            return {
                item['symbol']
                for item in data.get('symbols', [])
                if item.get("contractType") == "PERPETUAL"
                and item.get("quoteAsset") == "USDT"
                and item.get("status") == "TRADING"
            }
        except requests.exceptions.RequestException as e:
            print(f"❗ [{attempt}/{max_retries}] Binance 심볼 요청 실패: {e}")
            if attempt < max_retries:
                sleep(delay)
            else:
                print("❌ 최대 재시도 횟수 도달 → 빈 세트 반환")
                return set()


def get_binance_prices():
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return {item['symbol']: float(item['price']) for item in response.json()}
    except requests.exceptions.RequestException as e:
        print(f"❌ Binance 가격 요청 실패: {e}")
        return {}

def get_bybit_prices():
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # HTTPError 예외 유발
        data = response.json().get("result", {}).get("list", [])
        return {item['symbol']: float(item['lastPrice']) for item in data}, set(item['symbol'] for item in data)
    except requests.exceptions.RequestException as e:
        print(f"❌ Bybit 가격 요청 실패: {e}")
        return {}, set()

def get_bybit_24h_volumes():
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json().get("result", {}).get("list", [])
        return {
            item['symbol']: float(item.get('turnover24h', 0))  # quoteVolume 기준 (USDT)
            for item in data
        }
    except Exception as e:
        print(f"❌ Bybit 거래량 조회 실패: {e}")
        return {}

def fetch_spread_data():
    binance_symbols = get_binance_futures_symbols()
    # print(f"🪙 Binance 심볼 수: {len(binance_symbols)}")

    binance_prices = get_binance_prices()
    bybit_prices, bybit_symbols = get_bybit_prices()
    # print(f"📦 Bybit 심볼 수: {len(bybit_symbols)}")



    common_symbols = binance_symbols & bybit_symbols
    # print(f"🔗 공통 심볼 수 (가격 기준): {len(common_symbols)}")

    bybit_volumes = get_bybit_24h_volumes()
    volume_filtered = [s for s in common_symbols if bybit_volumes.get(s, 0) >= MIN_VOLUME_USDT]
    # print(f"💰 거래량 기준 통과: {len(volume_filtered)}")

    volume_ranked = sorted(
        [(s, bybit_volumes.get(s, 0)) for s in common_symbols if bybit_volumes.get(s, 0) >= MIN_VOLUME_USDT],
        key=lambda x: x[1],
        reverse=True
    )

    top_symbols = [s for s, _ in volume_ranked[:TOP_SYMBOL_LIMIT]]

    valid_symbols = []
    for symbol in top_symbols:
        if symbol in binance_prices and symbol in bybit_prices:
            if convert_symbol(binance, symbol) and convert_symbol(bybit, symbol):
                valid_symbols.append(symbol)
    # print(f"✅ 최종 사용 가능 심볼 수: {len(valid_symbols)}")

    spread_list = []
    for symbol in valid_symbols:
        b_price = binance_prices[symbol]
        y_price = bybit_prices[symbol]
        raw_spread_pct = (b_price - y_price) / min(b_price, y_price) * 100  # ✅ 방향성 포함
        spread_list.append({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "binance": b_price,
            "bybit": y_price,
            "spread_pct": round(raw_spread_pct, 4),
            "abs_spread_pct": round(abs(raw_spread_pct), 4)  # ✅ 진입 조건용
        })

    return sorted(spread_list, key=lambda x: abs(x["spread_pct"]), reverse=True)


#
# def get_filled_amount(exchange, order_id, symbol, params=None):
#     try:
#         closed_orders = exchange.fetch_closed_orders(symbol, params=params)
#         for o in closed_orders:
#             if o['id'] == order_id:
#                 return float(o.get('filled', 0))
#     except Exception as e:
#         print(f"❌ 주문 체결 확인 실패: {e}")
#     return 0
def get_filled_amount(exchange, order_id, symbol, params=None):
    try:
        # Bybit는 fetch_order() 시 acknowledged 옵션 필요
        if exchange.id == 'bybit':
            if params is None:
                params = {}
            params['acknowledged'] = True

        order = exchange.fetch_order(order_id, symbol, params=params)
        return float(order.get('filled', 0))
    except Exception as e:
        print(f"❌ 주문 체결 확인 실패 (fetch_order): {e}")
    return 0




def should_enter_position(symbol, spread_pct):
    recent_spread_history[symbol].append(spread_pct)
    if len(recent_spread_history[symbol]) == spread_hold_count:
        if all(abs(s) >= spread_threshold for s in recent_spread_history[symbol]):  # ✅ 변경됨
            if len(top1_history[symbol]) == spread_hold_count and all(top1_history[symbol]):
                return True
    return False

def round_quantity_to_step(exchange, symbol, qty):
    market = exchange.market(symbol)
    raw_precision = market.get("precision", {}).get("amount", 2)
    try:
        precision = int(raw_precision)
    except (TypeError, ValueError):
        precision = 2  # 기본값 설정

    step_size = market.get("limits", {}).get("amount", {}).get("min", 10 ** -precision)
    adjusted_qty = max(round(qty - (qty % step_size), precision), step_size)
    return adjusted_qty

def safe_set_leverage(exchange, symbol, leverage):
    try:
        params = {'category': 'linear'} if exchange.id == 'bybit' else {}
        markets = exchange.load_markets(params=params)

        normalized_symbol = None
        input_clean = symbol.replace('/', '').replace(':', '').upper()

        # (1) 우선: 선물/스왑 마켓에서 매칭
        for market_symbol, m in markets.items():
            market_clean = market_symbol.replace('/', '').replace(':', '').upper()
            if market_clean == input_clean and m.get('contract') and (m.get('swap') or m.get('future')):
                normalized_symbol = market_symbol
                break

        # (2) 일반 매칭
        if not normalized_symbol:
            for market_symbol in markets:
                market_clean = market_symbol.replace('/', '').replace(':', '').upper()
                if market_clean == input_clean:
                    normalized_symbol = market_symbol
                    break

        # (3) Bybit 특수 케이스 처리
        if not normalized_symbol and exchange.id == 'bybit':
            input_clean_retry = (symbol + ":USDT").replace('/', '').replace(':', '').upper()
            for market_symbol in markets:
                market_clean = market_symbol.replace('/', '').replace(':', '').upper()
                if market_clean == input_clean_retry:
                    normalized_symbol = market_symbol
                    break

        if not normalized_symbol:
            print(f"❌ {exchange.id.upper()} | 유효 심볼 찾기 실패: {symbol}")
            return

        market_info = markets.get(normalized_symbol, {})
        if exchange.id == 'bybit' and not (market_info.get('contract') and (market_info.get('swap') or market_info.get('future'))):
            return

        try:
            exchange.set_leverage(leverage, normalized_symbol, params=params)
            print(f"🎯 레버리지 설정 완료: {exchange.id.upper()} | {normalized_symbol} | {leverage}배")
        except Exception as e:
            if "leverage not modified" not in str(e):
                print(f"❌ 레버리지 설정 실패 ({exchange.id.upper()}, {normalized_symbol}): {e}")
    except Exception as e:
        print(f"❌ 레버리지 설정 실패 ({exchange.id.upper()}, {symbol}): {e}")




def enter_position(symbol, b_price, y_price, spread_pct):
    higher_exchange, lower_exchange = (binance, bybit) if b_price > y_price else (bybit, binance)
    higher_name, lower_name = ("binance", "bybit") if b_price > y_price else ("bybit", "binance")

    lower_symbol = convert_symbol(lower_exchange, symbol)
    higher_symbol = convert_symbol(higher_exchange, symbol)

    if not lower_symbol or not higher_symbol:
        print(f"⛔️ 유효하지 않은 심볼 → 건너뜀: {symbol}")
        return

    try:
        bybit_params = {'category': 'linear'}

        safe_set_leverage(lower_exchange, lower_symbol, 1)
        safe_set_leverage(higher_exchange, higher_symbol, 1)

        if lower_exchange.id == 'bybit':
            lower_exchange.set_margin_mode('isolated', lower_symbol, params=bybit_params)
        if higher_exchange.id == 'bybit':
            higher_exchange.set_margin_mode('isolated', higher_symbol, params=bybit_params)

        lower_price = b_price if lower_exchange == binance else y_price
        higher_price = b_price if higher_exchange == binance else y_price
        target_usdt = 100

        lower_qty = calculate_qty_for_fixed_usdt(lower_exchange, lower_symbol, lower_price, target_usdt)
        higher_qty = calculate_qty_for_fixed_usdt(higher_exchange, higher_symbol, higher_price, target_usdt)
        qty = max(lower_qty, higher_qty)

        qty = round_quantity_to_step(lower_exchange, lower_symbol, qty)
        qty = round_quantity_to_step(higher_exchange, higher_symbol, qty)

        buy_price = lower_price * 1.001
        sell_price = higher_price * 0.999

        def check_balance(exchange, asset='USDT'):
            try:
                balance = exchange.fetch_balance(params={'type': 'future'})
                return balance.get('free', {}).get(asset, 0)
            except Exception as e:
                print(f"❌ 잔고 확인 실패 ({exchange.id}): {e}")
                return 0

        usdt_required = target_usdt * 1.2
        lower_balance = check_balance(lower_exchange)
        higher_balance = check_balance(higher_exchange)

        if lower_balance < usdt_required or higher_balance < usdt_required:
            print(
                f"⛔️ 잔고 부족: {symbol} | 필요: {usdt_required:.2f} | "
                f"{lower_exchange.id.upper()}: {lower_balance:.4f} | "
                f"{higher_exchange.id.upper()}: {higher_balance:.4f}"
            )
            return

        print("=" * 60)
        print(
            f"🚀 진입: {symbol} | 수량: {qty} | 롱: {lower_name} | 숏: {higher_name} | "
            f"가격 B={b_price}, Y={y_price} | 스프레드={spread_pct:+.2f}%"
        )
        long_params = bybit_params if lower_exchange.id == 'bybit' else {}
        short_params = bybit_params if higher_exchange.id == 'bybit' else {}

        long_order = lower_exchange.create_limit_buy_order(lower_symbol, qty, buy_price, params=long_params)
        short_order = higher_exchange.create_limit_sell_order(higher_symbol, qty, sell_price, params=short_params)

        # ✅ 체결 대기용으로 pending_orders에 저장
        pending_orders[symbol] = {
            "long_exchange": lower_exchange,
            "short_exchange": higher_exchange,
            "long_symbol": lower_symbol,
            "short_symbol": higher_symbol,
            "qty": qty,
            "long_order_id": long_order['id'],
            "short_order_id": short_order['id'],
            "entry_spread": abs(spread_pct),
            "entry_spread_signed": spread_pct,
            "timestamp": time.time(),
            "entry_price_long": buy_price if lower_exchange == binance else y_price,
            "entry_price_short": sell_price if higher_exchange == binance else y_price
        }

        print(f"⏳ 지정가 주문 완료 → 체결 대기 중 (symbol: {symbol})")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"❌ 진입 실패: {e}")
        traceback.print_exc()



def exit_position(symbol, current_spread):
    pos = open_positions.get(symbol)
    if not pos:
        return

    print(f"💸 청산 시도: {symbol} | 현재 스프레드: {current_spread:.2f}% | 진입 스프레드: {pos['entry_spread']:.2f}%")

    try:
        long_exchange = pos['long_exchange']
        short_exchange = pos['short_exchange']
        long_symbol = pos['long_symbol']
        short_symbol = pos['short_symbol']
        long_qty = float(pos['long_qty'])
        short_qty = float(pos['short_qty'])

        # 🔄 심볼 포맷 보정: ccxt 표준 포맷으로 변환 보장
        long_symbol = convert_symbol(long_exchange, long_symbol) or long_symbol
        short_symbol = convert_symbol(short_exchange, short_symbol) or short_symbol

        print(f"🔍 롱심볼: {long_symbol}, 숏심볼: {short_symbol}")

        # Bybit는 category 파라미터 필요
        long_params = {'category': 'linear'} if long_exchange.id == 'bybit' else {}
        short_params = {'category': 'linear'} if short_exchange.id == 'bybit' else {}

        # 현재가 기준 지정가 청산 또는 시장가 청산 fallback
        try:
            long_ticker = long_exchange.fetch_ticker(long_symbol, params=long_params)
            short_ticker = short_exchange.fetch_ticker(short_symbol, params=short_params)
            long_bid = long_ticker.get('bid')
            short_ask = short_ticker.get('ask')
        except Exception as e:
            print(f"⚠️ 호가 정보 조회 실패: {e}")
            long_bid, short_ask = None, None

        use_market_order = long_bid is None or short_ask is None

        if use_market_order:
            print("⚠️ 호가 없음 → 시장가 청산 시도")
            long_order = long_exchange.create_market_sell_order(long_symbol, long_qty, params=long_params)
            short_order = short_exchange.create_market_buy_order(short_symbol, short_qty, params=short_params)
        else:
            long_limit_price = long_bid * 0.999
            short_limit_price = short_ask * 1.001
            long_order = long_exchange.create_limit_sell_order(long_symbol, long_qty, long_limit_price, params=long_params)
            short_order = short_exchange.create_limit_buy_order(short_symbol, short_qty, short_limit_price, params=short_params)

        time.sleep(1.5)
        long_filled = long_order.get('filled') or get_filled_amount(long_exchange, long_order['id'], long_symbol, long_params)
        short_filled = short_order.get('filled') or get_filled_amount(short_exchange, short_order['id'], short_symbol, short_params)


        long_avg = long_order.get('average') or get_order_average_price(long_exchange, long_order['id'], long_symbol,
                                                                        long_params)
        short_avg = short_order.get('average') or get_order_average_price(short_exchange, short_order['id'],
                                                                          short_symbol, short_params)

        print(f"✅ 청산 완료 | 롱: {long_filled}개 @ {long_avg or 'N/A'} | 숏: {short_filled}개 @ {short_avg or 'N/A'}")

        #
        #
        # print(f"✅ 롱 청산: {long_filled}개 @ {long_order.get('average', 'N/A')}")
        # print(f"✅ 숏 청산: {short_filled}개 @ {short_order.get('average', 'N/A')}")

        del open_positions[symbol]

    except Exception as e:
        print(f"❌ 청산 실패 ({symbol}): {e}")
        traceback.print_exc()



#
# def exit_position(symbol, current_spread):
#     pos = open_positions.get(symbol)
#     if not pos:
#         return
#
#     print(f"💸 청산 시도: {symbol} | 현재 스프레드: {current_spread:.2f}% | 진입 스프레드: {pos['entry_spread']:.2f}%")
#
#     try:
#         long_exchange = pos['long_exchange']
#         short_exchange = pos['short_exchange']
#         long_symbol = pos['long_symbol']
#         short_symbol = pos['short_symbol']
#         long_qty = float(pos['long_qty'])
#         short_qty = float(pos['short_qty'])
#
#         # params for Bybit
#         long_params = {'category': 'linear'} if long_exchange.id == 'bybit' else {}
#         short_params = {'category': 'linear'} if short_exchange.id == 'bybit' else {}
#
#         # # 청산 주문
#         # long_order = long_exchange.create_market_sell_order(long_symbol, long_qty, params=long_params)
#         # short_order = short_exchange.create_market_buy_order(short_symbol, short_qty, params=short_params)
#
#         # ✅ 변경: 지정가 청산
#         # 현재가 기준 약간 유리한 가격으로 지정가 주문
#         try:
#             long_ticker = long_exchange.fetch_ticker(long_symbol)
#             short_ticker = short_exchange.fetch_ticker(short_symbol)
#             long_bid = long_ticker.get('bid')
#             short_ask = short_ticker.get('ask')
#         except Exception as e:
#             print(f"⚠️ 호가 정보 조회 실패: {e}")
#             long_bid, short_ask = None, None
#         use_market_order = long_bid is None or short_ask is None
#
#         if use_market_order:
#             print("⚠️ 호가 없음 → 시장가 청산 시도")
#             long_order = long_exchange.create_market_sell_order(long_symbol, long_qty, params=long_params)
#             short_order = short_exchange.create_market_buy_order(short_symbol, short_qty, params=short_params)
#         else:
#             long_limit_price = long_bid * 0.999
#             short_limit_price = short_ask * 1.001
#
#             long_order = long_exchange.create_limit_sell_order(long_symbol, long_qty, long_limit_price, params=long_params)
#             short_order = short_exchange.create_limit_buy_order(short_symbol, short_qty, short_limit_price, params=short_params)
#
#         # filled 확인: fallback to fetch_closed_orders
#         time.sleep(1.5)
#         long_filled = long_order.get('filled') or get_filled_amount(long_exchange, long_order['id'], long_symbol, long_params)
#         short_filled = short_order.get('filled') or get_filled_amount(short_exchange, short_order['id'], short_symbol, short_params)
#
#         print(f"✅ 롱 청산: {long_filled}개 @ {long_order.get('average', 'N/A')}")
#         print(f"✅ 숏 청산: {short_filled}개 @ {short_order.get('average', 'N/A')}")
#
#         del open_positions[symbol]
#
#     except Exception as e:
#         print(f"❌ 청산 실패 ({symbol}): {e}")
#         traceback.print_exc()

csv_filename = "spread_log.csv"
with open(csv_filename, mode='w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Time", "Symbol", "Binance Price", "Bybit Price", "Spread %"])

spread_log_buffer = []
flush_every = 3
loop_count = 0

print("🔁 스프레드 모니터링 시작... (5초 간격)\n")
initial_spreads = fetch_spread_data()

print(f"📊 공통 종목 수: {len(initial_spreads)}개\n")


try:
    while True:
        all_spreads = fetch_spread_data()
        top_3 = all_spreads[:3]

        # ✅ Top1 기록
        if top_3:
            top1_symbol = top_3[0]['symbol']
            top1_history[top1_symbol].append(True)
            for item in top_3[1:]:
                top1_history[item['symbol']].append(False)

        now = datetime.utcnow().strftime('%H:%M:%S')
        print(f"[{now}] 🔝 Top3 스프레드: ", " | ".join([
            f"{item['symbol']} ({(item['binance'] - item['bybit']) / min(item['binance'], item['bybit']) * 100:+.2f}%)"
            for item in top_3
        ]))

        filtered = [item for item in all_spreads if abs(item['spread_pct']) >= spread_threshold]

        for symbol in list(pending_orders):

            MAX_LOSS_PCT = -10

            pending = pending_orders[symbol]

            long_exchange = pending['long_exchange']
            short_exchange = pending['short_exchange']
            long_symbol = pending['long_symbol']
            short_symbol = pending['short_symbol']
            qty = pending['qty']

            long_params = {'category': 'linear'} if long_exchange.id == 'bybit' else {}
            short_params = {'category': 'linear'} if short_exchange.id == 'bybit' else {}

            long_filled = get_filled_amount(long_exchange, pending['long_order_id'], long_symbol, long_params)
            short_filled = get_filled_amount(short_exchange, pending['short_order_id'], short_symbol, short_params)

            long_pending_qty = qty - long_filled
            short_pending_qty = qty - short_filled

            print(
                f"🕐 Pending {symbol} | "
                f"{long_exchange.id.upper()} 롱: {long_filled:.4f}/{long_pending_qty:.4f} | "
                f"{short_exchange.id.upper()} 숏: {short_filled:.4f}/{short_pending_qty:.4f}"
            )
            # 🔧 long/short 체결 확인 후 재확인 로직 추가
            if long_filled < 1e-8 or short_filled < 1e-8:
                sleep(1)  # 체결 반영까지 기다림
                if long_filled < 1e-8:
                    long_filled = get_filled_amount(long_exchange, pending['long_order_id'], long_symbol, long_params)
                if short_filled < 1e-8:
                    short_filled = get_filled_amount(short_exchange, pending['short_order_id'], short_symbol,
                                                     short_params)

            # 롱만 체결, 숏 미체결
            if long_filled > 0 and short_filled < 1e-8:
                try:
                    ticker = long_exchange.fetch_ticker(long_symbol, params=long_params)
                    current_price = ticker['last']
                    entry_price = pending.get("entry_price_long")
                    loss_pct = (current_price - entry_price) / entry_price * 100
                    if loss_pct <= MAX_LOSS_PCT:
                        print(f"❌ [손절] 롱 포지션 -10% 손실 도달 → 시장가 청산: {symbol}")
                        long_exchange.create_market_sell_order(long_symbol, qty, params=long_params)
                        del pending_orders[symbol]
                        continue
                except Exception as e:
                    print(f"❌ 손절 중 예외 발생 (롱): {e}")

            # 숏만 체결, 롱 미체결
            elif short_filled > 0 and long_filled < 1e-8:
                try:
                    ticker = short_exchange.fetch_ticker(short_symbol, params=short_params)
                    current_price = ticker['last']
                    entry_price = pending.get("entry_price_short")
                    loss_pct = (entry_price - current_price) / entry_price * 100
                    if loss_pct <= MAX_LOSS_PCT:
                        print(f"❌ [손절] 숏 포지션 -10% 손실 도달 → 시장가 청산: {symbol}")
                        short_exchange.create_market_buy_order(short_symbol, qty, params=short_params)
                        del pending_orders[symbol]
                        continue
                except Exception as e:
                    print(f"❌ 손절 중 예외 발생 (숏): {e}")


            # ✅ 한 쪽만 체결된 경우
            if (long_filled > 0 and short_filled < 1e-8) or (long_filled < 1e-8 and short_filled > 0):
                current_spreads = fetch_spread_data()
                spread_info = next((item for item in current_spreads if item['symbol'] == symbol), None)

                # if spread_info and abs(spread_info['spread_pct']) >= spread_threshold:
                if spread_info:  # ✅ spread_threshold 조건 제거!

                    print(f"⚡️ 단일 체결 감지 → 시장가 대응 체결 시도: {symbol}")

                    try:
                        if long_filled > 0:
                            sleep(1)  # 🔧 추가
                            short_order = short_exchange.create_market_sell_order(short_symbol, qty,
                                                                                  params=short_params)
                            short_filled = short_order.get('filled') or get_filled_amount(short_exchange,
                                                                                          short_order['id'],
                                                                                          short_symbol, short_params)
                        else:
                            sleep(1)  # 🔧 추가
                            long_order = long_exchange.create_market_buy_order(long_symbol, qty, params=long_params)
                            long_filled = long_order.get('filled') or get_filled_amount(long_exchange, long_order['id'],
                                                                                        long_symbol, long_params)

                        if long_filled > 0 and short_filled > 0:
                            open_positions[symbol] = {
                                "entry_spread": pending["entry_spread"],
                                "entry_spread_signed": pending["entry_spread_signed"],
                                "long_exchange": long_exchange,
                                "short_exchange": short_exchange,
                                "long_symbol": long_symbol,
                                "short_symbol": short_symbol,
                                "long_qty": long_filled,
                                "short_qty": short_filled
                            }
                            del pending_orders[symbol]
                            print(f"✅ 대응 체결 완료 → 포지션 등록: {symbol}")
                        else:
                            print(f"⏳ 대응 체결 미완 → 다음 루프에서 재확인: {symbol}")  # 🔧 추가


                    except Exception as e:
                        print(f"❌ 시장가 대응 실패: {e}")
            elif long_filled > 0 and short_filled > 0:
                open_positions[symbol] = {
                    "entry_spread": pending["entry_spread"],
                    "entry_spread_signed": pending["entry_spread_signed"],
                    "long_exchange": long_exchange,
                    "short_exchange": short_exchange,
                    "long_symbol": long_symbol,
                    "short_symbol": short_symbol,
                    "long_qty": long_filled,
                    "short_qty": short_filled
                }
                del pending_orders[symbol]
                print(f"✅ 지정가 쌍방 체결 → 포지션 등록: {symbol}")
            else:
                print(f"⏳ 체결 대기 중: {symbol} (롱: {long_filled}, 숏: {short_filled})")




        # ✅ 진입 조건 확인
        for item in filtered:
            symbol = item['symbol']
            spread_pct = item['spread_pct']

            recent_spread_history[symbol].append(spread_pct)

            if symbol not in open_positions and symbol not in pending_orders and len(open_positions) < 3:
                if should_enter_position(symbol, spread_pct):
                    print(f"🟢 조건 충족: {symbol} → 진입 시도")
                    enter_position(symbol, item['binance'], item['bybit'], spread_pct)

            spread_log_buffer.append([
                item["timestamp"], item["symbol"], item["binance"], item["bybit"], item["spread_pct"]
            ])

        # ✅ 청산 조건 확인
        for pos_symbol in list(open_positions):
            if pos_symbol in pending_orders:
                continue

            current = next((item for item in all_spreads if item['symbol'] == pos_symbol), None)
            if not current:
                continue

            pos = open_positions[pos_symbol]
            if pos['long_qty'] < 1e-8 or pos['short_qty'] < 1e-8:
                print(f"⏸ 청산 생략: {pos_symbol} → 한쪽만 체결된 상태로 감지됨 (롱: {pos['long_qty']}, 숏: {pos['short_qty']})")
                continue
            current_spread = current['spread_pct']
            entry_spread = open_positions[pos_symbol]['entry_spread']
            entry_spread_signed = open_positions[pos_symbol].get('entry_spread_signed', current_spread)

            binance_price = current['binance']
            bybit_price = current['bybit']
            long_exchange_id = open_positions[pos_symbol]['long_exchange'].id
            short_exchange_id = open_positions[pos_symbol]['short_exchange'].id

            current_direction = 'binance>bybit' if binance_price > bybit_price else 'bybit>binance'
            original_direction = 'binance>bybit' if long_exchange_id == 'bybit' else 'bybit>binance'

            spread_reversal_stoploss = (
                abs(current_spread - entry_spread_signed) > exit_percent and
                (current_spread * entry_spread_signed < 0)
            )
            spread_reversion = abs(current_spread) < entry_spread - exit_percent

            exit_triggered = spread_reversal_stoploss or spread_reversion
            exit_condition_history[pos_symbol].append(exit_triggered)

            print(f"→ {pos_symbol}: 현재 {current_spread:.2f}% / 진입 {entry_spread_signed:.2f}% | 청산조건: {exit_condition_history[pos_symbol]}")

            if len(exit_condition_history[pos_symbol]) == spread_hold_count and all(exit_condition_history[pos_symbol]):
                reason = "방향 반전 손절" if spread_reversal_stoploss else "스프레드 축소"
                print(f"⚠️ 청산 조건 {spread_hold_count}회 지속 충족 ({reason}) → 청산 실행")
                exit_position(pos_symbol, current_spread)
                exit_condition_history[pos_symbol].clear()

        # ✅ 로그 저장 주기
        loop_count += 1
        if loop_count % flush_every == 0 and spread_log_buffer:
            with open(csv_filename, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(spread_log_buffer)
            print(f"💾 {len(spread_log_buffer)}개 기록 저장됨.")
            spread_log_buffer.clear()

        time.sleep(5)

except KeyboardInterrupt:
    print("\n⛔️ 모니터링 종료됨.")
    if spread_log_buffer:
        with open(csv_filename, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(spread_log_buffer)
        print(f"💾 종료 시 {len(spread_log_buffer)}개 저장 완료.")
except Exception as e:
    print("❌ 예외 발생:", e)
    traceback.print_exc()
    if spread_log_buffer:
        with open(csv_filename, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(spread_log_buffer)
        print(f"💾 예외 발생 시 {len(spread_log_buffer)}개 저장 완료.")


