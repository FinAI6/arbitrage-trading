"""
Arbitrage trading module for cryptocurrency exchanges
"""

import requests
import time
import csv
from datetime import datetime
import os
import ccxt
from dotenv import load_dotenv
import traceback
from collections import defaultdict, deque

# Load environment variables
load_dotenv()

# Exchange configurations
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

# Trading parameters
spread_threshold = 1.0
exit_percent = 0.9
spread_hold_count = 2  # 스프레드 지속 조건 횟수, Top 1 연속 횟수
TOP_SYMBOL_LIMIT = 300  # 거래량 상위 몇 개 종목만 사용할지 설정/ 전체종목개수 381개
MIN_VOLUME_USDT = 5_000_000  # 24시간 거래대금 최소 기준

# State management
recent_spread_history = defaultdict(lambda: deque(maxlen=spread_hold_count))
open_positions = {}
top1_history = defaultdict(lambda: deque(maxlen=spread_hold_count))

def convert_symbol(exchange, raw_symbol):
    """Convert raw symbol to exchange-specific format"""
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
    """Calculate quantity for fixed USDT amount"""
    market = exchange.market(symbol)
    qty = target_usdt / price
    precision = int(market.get('precision', {}).get('amount', 2))
    return round(qty, precision)

def get_binance_futures_symbols():
    """Get list of available Binance futures symbols"""
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
    """Get current prices from Binance"""
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    return {item['symbol']: float(item['price']) for item in requests.get(url).json()}

def get_bybit_prices():
    """Get current prices from Bybit"""
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json().get("result", {}).get("list", [])
        return {item['symbol']: float(item['lastPrice']) for item in data}, set(item['symbol'] for item in data)
    except requests.exceptions.RequestException as e:
        print(f"❌ Bybit 가격 요청 실패: {e}")
        return {}, set()

def get_bybit_24h_volumes():
    """Get 24h trading volumes from Bybit"""
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json().get("result", {}).get("list", [])
        return {
            item['symbol']: float(item.get('turnover24h', 0))
            for item in data
        }
    except Exception as e:
        print(f"❌ Bybit 거래량 조회 실패: {e}")
        return {}

def fetch_spread_data():
    """Fetch and process spread data between exchanges"""
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
        raw_spread_pct = (b_price - y_price) / min(b_price, y_price) * 100
        spread_list.append({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "binance": b_price,
            "bybit": y_price,
            "spread_pct": round(raw_spread_pct, 4),
            "abs_spread_pct": round(abs(raw_spread_pct), 4)
        })

    return sorted(spread_list, key=lambda x: abs(x["spread_pct"]), reverse=True)

def get_filled_amount(exchange, order_id, symbol, params=None):
    """Get filled amount for an order"""
    try:
        closed_orders = exchange.fetch_closed_orders(symbol, params=params)
        for o in closed_orders:
            if o['id'] == order_id:
                return float(o.get('filled', 0))
    except Exception as e:
        print(f"❌ 주문 체결 확인 실패: {e}")
    return 0

def should_enter_position(symbol, spread_pct):
    """Check if we should enter a position based on spread conditions"""
    recent_spread_history[symbol].append(spread_pct)
    if len(recent_spread_history[symbol]) == spread_hold_count:
        if all(abs(s) >= spread_threshold for s in recent_spread_history[symbol]):
            if len(top1_history[symbol]) == spread_hold_count and all(top1_history[symbol]):
                return True
    return False

def safe_set_leverage(exchange, symbol, leverage):
    """Safely set leverage for a position"""
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
    """Enter a new arbitrage position"""
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

        def check_balance(exchange, asset='USDT'):
            try:
                if exchange.id == 'bybit':
                    balance = exchange.fetch_balance(params={'type': 'future'})
                elif exchange.id == 'binance':
                    balance = exchange.fetch_balance(params={'type': 'future'})
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

        long_params = bybit_params if lower_exchange.id == 'bybit' else {}
        short_params = bybit_params if higher_exchange.id == 'bybit' else {}

        long_order = lower_exchange.create_market_buy_order(lower_symbol, qty, params=long_params)
        short_order = higher_exchange.create_market_sell_order(higher_symbol, qty, params=short_params)

        # Store position information
        open_positions[symbol] = {
            'long_exchange': lower_exchange.id,
            'short_exchange': higher_exchange.id,
            'long_symbol': lower_symbol,
            'short_symbol': higher_symbol,
            'quantity': qty,
            'entry_spread': spread_pct,
            'entry_time': datetime.utcnow()
        }

    except Exception as e:
        print(f"❌ 포지션 진입 실패 ({symbol}): {e}")
        traceback.print_exc()

def exit_position(symbol, current_spread):
    """Exit an existing arbitrage position"""
    if symbol not in open_positions:
        return

    position = open_positions[symbol]
    try:
        long_exchange = binance if position['long_exchange'] == 'binance' else bybit
        short_exchange = binance if position['short_exchange'] == 'binance' else bybit

        bybit_params = {'category': 'linear'}

        # Close long position
        long_params = bybit_params if long_exchange.id == 'bybit' else {}
        long_exchange.create_market_sell_order(
            position['long_symbol'],
            position['quantity'],
            params=long_params
        )

        # Close short position
        short_params = bybit_params if short_exchange.id == 'bybit' else {}
        short_exchange.create_market_buy_order(
            position['short_symbol'],
            position['quantity'],
            params=short_params
        )

        print(f"✅ 포지션 종료: {symbol}")
        print(f"   ↳ 진입 스프레드: {position['entry_spread']:+.2f}%")
        print(f"   ↳ 종료 스프레드: {current_spread:+.2f}%")
        print(f"   ↳ 보유 시간: {datetime.utcnow() - position['entry_time']}")

        del open_positions[symbol]

    except Exception as e:
        print(f"❌ 포지션 종료 실패 ({symbol}): {e}")
        traceback.print_exc() 