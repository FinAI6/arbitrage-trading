import requests
import time
import csv
from datetime import datetime
import os
import ccxt
from dotenv import load_dotenv
import traceback
from collections import defaultdict, deque

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
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})

spread_threshold = 1.0
exit_percent = 0.9
spread_hold_count = 2  # 스프레드 지속 조건 횟수, Top 1 연속 횟수
TOP_SYMBOL_LIMIT = 300  # 거래량 상위 몇 개 종목만 사용할지 설정/ 전체종목개수 381개
MIN_VOLUME_USDT = 5_000_000 #10_000_000  # ✅ 24시간 거래대금 최소 기준 (예: 1천만 USDT 이상)

recent_spread_history = defaultdict(lambda: deque(maxlen=spread_hold_count))
open_positions = {}
top1_history = defaultdict(lambda: deque(maxlen=spread_hold_count))


def convert_symbol(exchange, raw_symbol):
    try:
        exchange.load_markets()
        formatted = raw_symbol.replace("/", "").upper()
        for market_id, market in exchange.markets.items():
            plain_id = market['id'].replace("/", "").upper()
            if plain_id == formatted:
                return market['symbol']
    except Exception as e:
        print(f"❌ [{exchange.id}] convert_symbol 실패: {raw_symbol} → {e}")
    return None


def calculate_qty_for_fixed_usdt(exchange, symbol, price, target_usdt=100):
    market = exchange.market(symbol)
    qty = target_usdt / price
    precision = int(market.get('precision', {}).get('amount', 2))
    return round(qty, precision)


def get_binance_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    data = requests.get(url).json()
    return set(
        item['symbol']
        for item in data.get('symbols', [])
        if item.get("contractType") == "PERPETUAL"
        and item.get("quoteAsset") == "USDT"
        and item.get("status") == "TRADING"
    )


def get_binance_prices():
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    return {item['symbol']: float(item['price']) for item in requests.get(url).json()}


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
    binance_prices = get_binance_prices()
    bybit_prices, bybit_symbols = get_bybit_prices()
    bybit_volumes = get_bybit_24h_volumes()

    common_symbols = binance_symbols & bybit_symbols

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



def get_filled_amount(exchange, order_id, symbol, params=None):
    try:
        closed_orders = exchange.fetch_closed_orders(symbol, params=params)
        for o in closed_orders:
            if o['id'] == order_id:
                return float(o.get('filled', 0))
    except Exception as e:
        print(f"❌ 주문 체결 확인 실패: {e}")
    return 0


def should_enter_position(symbol, spread_pct):
    recent_spread_history[symbol].append(spread_pct)
    if len(recent_spread_history[symbol]) == spread_hold_count:
        if all(abs(s) >= spread_threshold for s in recent_spread_history[symbol]):  # ✅ 변경됨
            if len(top1_history[symbol]) == spread_hold_count and all(top1_history[symbol]):
                return True
    return False



def safe_set_leverage(exchange, symbol, leverage):
    try:
        market = exchange.market(symbol)
        info = exchange.fetch_positions([symbol])
        for pos in info:
            if pos['symbol'] == symbol:
                current_leverage = pos.get('leverage')
                if current_leverage != leverage:
                    exchange.set_leverage(leverage, symbol, params={'category': 'linear'})

                else:
                    print(f"⚠️ 레버리지 이미 {leverage}배 설정됨 → 변경 생략 ({exchange.id}, {symbol})")
                return
    except Exception as e:
        print(f"❌ 레버리지 설정 중 오류 ({exchange.id}, {symbol}): {e}")

def enter_position(symbol, b_price, y_price, spread_pct):
    higher_exchange, lower_exchange = (binance, bybit) if b_price > y_price else (bybit, binance)
    higher_name, lower_name = ("binance", "bybit") if b_price > y_price else ("bybit", "binance")

    lower_symbol = convert_symbol(lower_exchange, symbol)
    higher_symbol = convert_symbol(higher_exchange, symbol)

    if not lower_symbol or not higher_symbol:
        print(f"⛔️ 유효하지 않은 심볼 → 건너뜀: {symbol}")
        return


    try:
        # category parameter for Bybit
        bybit_params = {'category': 'linear'}

        # 설정: 레버리지 + 마진모드
        safe_set_leverage(lower_exchange, lower_symbol, 1)
        safe_set_leverage(higher_exchange, higher_symbol, 1)

        if lower_exchange.id == 'bybit':
            lower_exchange.set_margin_mode('isolated', lower_symbol, params=bybit_params)
        if higher_exchange.id == 'bybit':
            higher_exchange.set_margin_mode('isolated', higher_symbol, params=bybit_params)

        # 수량 계산
        lower_price = b_price if lower_exchange == binance else y_price
        higher_price = b_price if higher_exchange == binance else y_price
        target_usdt = 100

        lower_qty = calculate_qty_for_fixed_usdt(lower_exchange, lower_symbol, lower_price, target_usdt)
        higher_qty = calculate_qty_for_fixed_usdt(higher_exchange, higher_symbol, higher_price, target_usdt)
        qty = max(lower_qty, higher_qty)

        # 잔고 확인
        def check_balance(exchange, asset='USDT'):
            try:
                if exchange.id == 'bybit':
                    balance = exchange.fetch_balance(params={'type': 'future'})
                elif exchange.id == 'binance':
                    balance = exchange.fetch_balance(params={'type': 'future'})  # 👈 이 줄 수정!
                else:
                    balance = exchange.fetch_balance()

                return balance.get('free', {}).get(asset, 0)
            except Exception as e:
                print(f"❌ 잔고 확인 실패 ({exchange.id}): {e}")
                return 0

        usdt_required = target_usdt * 1.2

        lower_balance = check_balance(lower_exchange)
        higher_balance = check_balance(higher_exchange)

        if check_balance(lower_exchange) < usdt_required or check_balance(higher_exchange) < usdt_required:
            print(f"⛔️ 잔고 부족 → 건너뜀: {symbol}")
            print(f"   ↳ 필요 USDT: {usdt_required:.2f}")
            print(f"   ↳ {lower_exchange.id} 잔고: {lower_balance:.4f} USDT")
            print(f"   ↳ {higher_exchange.id} 잔고: {higher_balance:.4f} USDT")
            return

        print("=" * 60)
        print(f"🚀 진입: {symbol} | 수량: {qty}")
        print(f"롱: {lower_name} | 숏: {higher_name}")
        print(f"가격: B={b_price}, Y={y_price} | 스프레드={spread_pct:+.2f}%")

        # 주문 실행
        long_params = bybit_params if lower_exchange.id == 'bybit' else {}
        short_params = bybit_params if higher_exchange.id == 'bybit' else {}

        long_order = lower_exchange.create_market_buy_order(lower_symbol, qty, params=long_params)
        short_order = higher_exchange.create_market_sell_order(higher_symbol, qty, params=short_params)

        # 체결 확인
        time.sleep(0.5)
        long_filled = long_order.get('filled')
        if not long_filled:
            try:
                pos = lower_exchange.fetch_position(lower_symbol, params=bybit_params if lower_exchange.id == 'bybit' else {})
                long_filled = abs(float(pos.get('contracts', 0)))
                print(f"📦 포지션에서 롱 수량 확인됨 → {long_filled}")
            except Exception as e:
                print(f"❌ 롱 수량 확인 실패: {e}")
                return

        # 숏 체결 수량 확인
        time.sleep(0.5)
        short_filled = short_order.get('filled')
        if not short_filled:
            short_filled = get_filled_amount(higher_exchange, short_order['id'], higher_symbol, short_params)
            if not short_filled:
                print(f"❌ 숏 체결 수량 확인 실패")
                return

        print(f"✅ 롱 체결 ({lower_name}): {long_filled}개")
        print(f"✅ 숏 체결 ({higher_name}): {short_filled}개")

        open_positions[symbol] = {
            "entry_spread": abs(spread_pct),
            "entry_spread_signed": spread_pct,
            "long_exchange": lower_exchange,
            "short_exchange": higher_exchange,
            "long_symbol": lower_symbol,
            "short_symbol": higher_symbol,
            "long_qty": float(long_filled),
            "short_qty": float(short_filled)
        }

    except Exception as e:
        print(f"❌ 진입 실패: {e}")
        traceback.print_exc()
    print("=" * 60 + "\n")


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

        # params for Bybit
        long_params = {'category': 'linear'} if long_exchange.id == 'bybit' else {}
        short_params = {'category': 'linear'} if short_exchange.id == 'bybit' else {}

        # 청산 주문
        long_order = long_exchange.create_market_sell_order(long_symbol, long_qty, params=long_params)
        short_order = short_exchange.create_market_buy_order(short_symbol, short_qty, params=short_params)

        # filled 확인: fallback to fetch_closed_orders
        time.sleep(1.5)
        long_filled = long_order.get('filled') or get_filled_amount(long_exchange, long_order['id'], long_symbol, long_params)
        short_filled = short_order.get('filled') or get_filled_amount(short_exchange, short_order['id'], short_symbol, short_params)

        print(f"✅ 롱 청산: {long_filled}개 @ {long_order.get('average', 'N/A')}")
        print(f"✅ 숏 청산: {short_filled}개 @ {short_order.get('average', 'N/A')}")

        del open_positions[symbol]

    except Exception as e:
        print(f"❌ 청산 실패 ({symbol}): {e}")
        traceback.print_exc()

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
        if top_3:
            top1_symbol = top_3[0]['symbol']
            top1_history[top1_symbol].append(True)

            for item in top_3[1:]:
                top1_history[item['symbol']].append(False)

        filtered = [item for item in all_spreads if abs(item['spread_pct']) >= spread_threshold]
        now = datetime.utcnow().strftime('%H:%M:%S')

        print(f"[{now}] 🔝 Top3 스프레드: ", " | ".join([
            f"{item['symbol']} ({(item['binance'] - item['bybit']) / min(item['binance'], item['bybit']) * 100:+.2f}%)"
            for item in top_3
        ]))

        for item in filtered:
            symbol = item['symbol']
            spread_pct = item['spread_pct']

            recent_spread_history[symbol].append(spread_pct)

            # 최대 종목 개수
            if symbol not in open_positions and len(open_positions) < 3 and should_enter_position(symbol, spread_pct):
                print(f"🟢 조건 충족: {symbol} 스프레드 지속성 확보 → 진입 시도")
                enter_position(symbol, item['binance'], item['bybit'], spread_pct)

            spread_log_buffer.append([
                item["timestamp"], item["symbol"], item["binance"], item["bybit"], item["spread_pct"]
            ])
        # if open_positions:
        #     for pos_symbol in list(open_positions):
        #         current = next((item for item in all_spreads if item['symbol'] == pos_symbol), None)
        #         if current:
        #             current_spread = current['spread_pct']
        #             entry_spread = open_positions[pos_symbol]['entry_spread']
        #             print(f"→ {pos_symbol}: 현재 {current_spread:.2f}% / 진입 {entry_spread:.2f}%")
        #             if current_spread < entry_spread - exit_percent:
        #                 exit_position(pos_symbol, current_spread)

        if open_positions:
            for pos_symbol in list(open_positions):
                current = next((item for item in all_spreads if item['symbol'] == pos_symbol), None)
                if not current:
                    continue

                current_spread = current['spread_pct']
                entry_spread = open_positions[pos_symbol]['entry_spread']
                entry_spread_signed = open_positions[pos_symbol].get('entry_spread_signed', current_spread)

                print(f"→ {pos_symbol}: 현재 {current_spread:.2f}% / 진입 {entry_spread_signed:.2f}%")

                # long/short이 어디서 들어갔는지 파악
                long_exchange_id = open_positions[pos_symbol]['long_exchange'].id
                short_exchange_id = open_positions[pos_symbol]['short_exchange'].id

                binance_price = current['binance']
                bybit_price = current['bybit']
                current_direction = 'binance>bybit' if binance_price > bybit_price else 'bybit>binance'
                original_direction = 'binance>bybit' if long_exchange_id == 'bybit' else 'bybit>binance'

                entry_spread = open_positions[pos_symbol]['entry_spread']
                entry_spread_signed = open_positions[pos_symbol].get('entry_spread_signed', current_spread)

                # ✅ 1. 방향 반전으로 손절: 스프레드가 반대 방향으로 exit_percent 이상 벌어졌는가?
                spread_reversal_stoploss = (
                        abs(current_spread - entry_spread_signed) > exit_percent and
                        (current_spread * entry_spread_signed < 0)
                )

                # ✅ 2. 축소 기준으로 익절
                spread_reversion = abs(current_spread) < entry_spread - exit_percent

                # ✅ 3. 방향 반전 감지
                direction_reversed = current_direction != original_direction

                if spread_reversal_stoploss or spread_reversion:
                    reason = "방향 반전 손절" if spread_reversal_stoploss else "스프레드 축소"
                    print(f"⚠️ 청산 조건 충족 ({reason}) → 청산 실행")
                    exit_position(pos_symbol, current_spread)

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
