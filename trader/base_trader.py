from abc import ABC, abstractmethod
from functools import wraps
import json
import math
from aggregation_manager import AggregationManager
from config_manager import ConfigManager
import ccxt.pro as ccxt


def status_decorator(state):
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            if self.status == state:
                print(f"🔄 [{self.symbol}] Status: {state} -> Executing {func.__name__}")
                return await func(self, *args, **kwargs)
            else:
                print(f"⚠️  [{self.symbol}] Skipping {func.__name__} - Current status: {self.status}, Required: {state}")
                return None
        return wrapper
    return decorator

class BaseTrader(ABC):
    def __init__(self, symbol: str, direction: bool, aggregation_manager: AggregationManager):
        self.symbol = symbol
        self.direction = direction
        self.aggregation_manager = aggregation_manager
        self.config_manager = ConfigManager()
        self.target_usdt = self.config_manager.getfloat('TRADING', 'target_usdt')

        self.binance = ccxt.binance({
            'apiKey': self.config_manager.get('EXCHANGE', 'binance_api_key'),
            'secret': self.config_manager.get('EXCHANGE', 'binance_api_secret'),
            'options': {'defaultType': 'future',
                        'adjustForTimeDifference': True},
            'enableRateLimit': True
        })

        self.bybit = ccxt.bybit({
            'apiKey': self.config_manager.get('EXCHANGE', 'bybit_api_key'),
            'secret': self.config_manager.get('EXCHANGE', 'bybit_api_secret'),
            'options': {'defaultType': 'future',
                        'adjustForTimeDifference': True},
            'enableRateLimit': True
        })

        self.enter_order_result: dict | None = {}
        self.enter_order_monitor_result: dict | None = {'info': {},
                                                'long': [],
                                                'short': []}

        self.exit_monitor_result: dict | None = {}
        self.exit_order_result: dict | None = {}
        self.exit_order_monitor_result: dict | None = {'info': {},
                                                       'long': [],
                                                       'short': []}

        self.status = "initialize"

    @status_decorator("initialize")
    async def initialize(self):
        # await self.binance.load_markets()
        # print("Finish loading Binance markets.")
        # await self.bybit.load_markets()
        # print("Finish loading Bybit markets.")
        self.status = "enter_order"

    @abstractmethod
    async def enter_order(self): ...

    @abstractmethod
    async def enter_order_monitor(self): ...

    @abstractmethod
    async def exit_monitor(self): ...

    @abstractmethod
    async def exit_order(self): ...

    @abstractmethod
    async def exit_order_monitor(self): ...

    @status_decorator("end")
    async def end(self):
        """모든 리소스 정리"""
        try:
            if hasattr(self, 'binance') and self.binance:
                await self.binance.close()
                print("✅ Binance 연결 종료")

            if hasattr(self, 'bybit') and self.bybit:
                await self.bybit.close()
                print("✅ Bybit 연결 종료")

        except Exception as e:
            print(f"리소스 정리 중 오류: {e}")

    def get_lastest_data(self):
        return self.aggregation_manager.get_lastest_spread_by_symbol(self.symbol)

    def calculate_spread_percent(self):
        data = self.aggregation_manager.get_lastest_spread_by_symbol(self.symbol)
        return (data['binance_price'] - data['bybit_price'])/min(data['binance_price'], data['bybit_price']) * 100

    def check_valid_spread(self):
        threshold = self.config_manager.getfloat('AGGREGATION', 'arb_threshold')
        spread_percent = self.calculate_spread_percent()
        if abs(spread_percent) >= abs(threshold):
            if (spread_percent > 0) and self.direction:
                return True
            elif (spread_percent < 0) and not self.direction:
                return True
            return False
        else:
            return False

    async def convert_symbol(self, exchange, raw_symbol):
        try:
            await exchange.load_markets()
            formatted = raw_symbol.replace("/", "").upper()
            for market_id, market in exchange.markets.items():
                plain_id = market['id'].replace("/", "").upper()
                if plain_id == formatted:
                    # Bybit의 경우 linear=False인 경우만 제외, 그 외는 허용
                    if exchange.id == 'bybit':
                        linear = market.get('linear')
                        if linear is False:
                            print(f"🚫 BYBIT 제외 (linear=False): {raw_symbol}")
                            return None
                        print(f"Bybit: {market['symbol']}")
                        return market['symbol']
                    else:
                        print(f"{exchange.id}: {market['symbol']}")
                        return market['symbol']
        except Exception as e:
            print(f"❌ [{exchange.id}] convert_symbol 실패: {raw_symbol} → {e}")
        return None

    async def calculate_qty_for_fixed_usdt(self, exchange, symbol, price, target_usdt):
        await exchange.load_markets()
        market = exchange.market(symbol)

        qty = target_usdt / price
        min_qty = self.calculate_min_qty(exchange, symbol, price)

        # precision = market.get("precision", {}).get("amount", 2)
        # log_precision = round(math.log10(precision))

        adjusted_qty = self.make_qty_step(market, qty, 'round')
        adjusted_min_qty = self.make_qty_step(market, min_qty, 'ceil')

        # Todo: 여기부터 검증
        # scale = 10 ** log_precision
        # adjusted_qty = round(qty / scale) * scale
        # adjusted_min_qty = math.ceil(min_qty / scale) * scale

        return max(adjusted_qty, adjusted_min_qty)

    def make_qty_step(self, market, qty, adjust_type):
        if adjust_type not in ['round', 'ceil']:
            adjust_type = 'round'

        precision = market.get("precision", {}).get("amount", 2)
        log_precision = round(math.log10(precision))

        scale = 10 ** log_precision
        if adjust_type == 'round':
            adjusted_qty = round(qty / scale) * scale
        else:
            adjusted_qty = math.ceil(qty / scale) * scale
        return adjusted_qty

    def calculate_min_qty(self, exchange, symbol, price):
        market = exchange.market(symbol)
        min_amount = market['limits']['amount']['min']
        min_cost = market['limits']['cost']['min']
        if min_cost is None:
            min_cost = 5.5
        return max(min_amount, min_cost / price)

        # precision = int(market.get('precision', {}).get('amount', 2))
        # return round(qty, precision)
        # market = exchange.market(symbol)
        # qty = target_usdt / price
        # precision = market.get('precision', {}).get('amount', 2)
        # minimal_qty = market.get('limits', {}).get('amount', {}).get('min', precision)
        # adjusted_qty = max(round(qty / precision) * precision, minimal_qty)
        # # precision = int(market.get('precision', {}).get('amount', 2))
        # return adjusted_qty

    # def round_quantity_to_step(self, exchange, symbol, qty):
    #     market = exchange.market(symbol)
    #     raw_precision = market.get("precision", {}).get("amount", 2)
    #     try:
    #         precision = int(raw_precision)
    #     except (TypeError, ValueError):
    #         precision = 2  # 기본값 설정
    #
    #     step_size = market.get("limits", {}).get("amount", {}).get("min", 10 ** -precision)
    #     adjusted_qty = max(round(qty - (qty % step_size), precision), step_size)
    #     return adjusted_qty

    async def check_balance(self, exchange, asset='USDT'):
        try:
            balance = await exchange.fetch_balance(params={'type': 'future'})
            return balance.get('free', {}).get(asset, 0)
        except Exception as e:
            print(f"❌ 잔고 확인 실패 ({exchange.id}): {e}")
            return 0

    async def check_order_status(self, exchange, symbol, order_id):
        if exchange.id == 'bybit':
            order_result = await exchange.fetch_open_order(id=order_id)
        elif exchange.id == 'binance':
            order_result = await exchange.fetch_order(id=order_id, symbol=symbol)
        else:
            raise Exception(f"Unknown exchange: {exchange.id}")
        return order_result

    async def safe_set_margin_mode(self, exchange, symbol: str, margin_mode: str):
        if margin_mode not in ['isolated', 'crossed']:
            print("Margin Type must be 'isolated' or 'crossed'. Skipping.")
            raise ValueError("Invalid margin type.")
        try:
            if exchange.id == 'binance':
                try:
                    await exchange.set_margin_mode(margin_mode, symbol)
                    print(f"{exchange.id} 마진 모드 설정 완료: {margin_mode}")
                except Exception as e:
                    print(f"Binance Set Margin Mode Exception: {e}")
            elif exchange.id == 'bybit':
                try:
                    await exchange.set_margin_mode(margin_mode, symbol, params={'category': 'linear'})
                    print(f"{exchange.id} 마진 모드 설정 완료: {margin_mode}")
                except Exception as e:
                    print(f"Bybit Set Margin Mode Exception: {e}")
                return
        except Exception as e:
            print(f"❌ 마진 모드 설정 중 오류 ({exchange.id}, {symbol}): {e}")

    async def safe_set_leverage(self, exchange, symbol, leverage):
        try:
            if exchange.id == 'binance':
                await exchange.set_leverage(leverage, symbol, params={'category': 'linear'})
                print(f"{exchange.id} 레버리지 설정 완료: {leverage}")
            elif exchange.id == 'bybit':
                try:
                    await exchange.set_leverage(leverage, symbol, params={'category': 'linear'})
                    print(f"{exchange.id} 레버리지 설정 완료: {leverage}")
                except Exception as e:
                    error_data = json.loads(e.args[0][e.args[0].find("{"):])
                    # e: {'retCode': 110043, 'retMsg': 'leverage not modified', 'result': {}, 'retExtInfo': {}, 'time': 1750833253619}
                    if error_data.get('retMsg') == 'leverage not modified':
                        print(f"⚠️ 레버리지 이미 {leverage}배 설정됨 → 변경 생략 ({exchange.id}, {symbol})")
                    else:
                        print(f"❌ 레버리지 설정 중 오류 ({exchange.id}, {symbol}): {e}")
                return
        except Exception as e:
            print(f"❌ 레버리지 설정 중 오류 ({exchange.id}, {symbol}): {e}")

    async def safe_cancel_order(self, exchange, symbol, order_id) -> None | dict:
        '''
        무조건 이 함수 내에서 order가 closed 된 상태로 내보냄.
        '''
        if exchange.id == 'binance':
            try:
                # {'info': {'orderId': '3947317476', 'symbol': 'LEVERUSDT', 'status': 'NEW', 'clientOrderId': 'x-cvBPrNm95a76ba186fddbe1117f821', 'price': '0.0003100', 'avgPrice': '0.00', 'origQty': '20000', 'executedQty': '0', 'cumQuote': '0.0000000', 'timeInForce': 'GTC', 'type': 'LIMIT', 'reduceOnly': False, 'closePosition': False, 'side': 'BUY', 'positionSide': 'BOTH', 'stopPrice': '0.0000000', 'workingType': 'CONTRACT_PRICE', 'priceProtect': False, 'origType': 'LIMIT', 'priceMatch': 'NONE', 'selfTradePreventionMode': 'EXPIRE_MAKER', 'goodTillDate': '0', 'time': '1751265066013', 'updateTime': '1751265066013'}, 'id': '3947317476', 'clientOrderId': 'x-cvBPrNm95a76ba186fddbe1117f821', 'timestamp': 1751265066013, 'datetime': '2025-06-30T06:31:06.013Z', 'lastTradeTimestamp': None, 'lastUpdateTimestamp': 1751265066013, 'symbol': 'LEVER/USDT:USDT', 'type': 'limit', 'timeInForce': 'GTC', 'postOnly': False, 'reduceOnly': False, 'side': 'buy', 'price': 0.00031, 'triggerPrice': None, 'amount': 20000.0, 'cost': 0.0, 'average': None, 'filled': 0.0, 'remaining': 20000.0, 'status': 'open', 'fee': None, 'trades': [], 'fees': [], 'stopPrice': None, 'takeProfitPrice': None, 'stopLossPrice': None}
                cancel_result = await exchange.cancel_order(order_id, symbol)
                result = await self.check_order_status(exchange, symbol, order_id)
                if result['status'] == 'canceled':
                    return result
            except Exception as e:
                error_data = json.loads(e.args[0][e.args[0].find("{"):])
                if 'Unknown order sent' in error_data['msg']:
                    result = await self.check_order_status(exchange, symbol, order_id)
                    if result['status'] == 'closed' or result['status'] == 'canceled':
                        return result
                else:
                    print(f"Binance Cancel Order Exception: {e}")
                    return None
        elif exchange.id == 'bybit':
            try:
                # {'info': {'orderId': '2932ea0a-7b8c-4d89-81c2-16108a6ee5de', 'orderLinkId': ''}, 'id': '2932ea0a-7b8c-4d89-81c2-16108a6ee5de', 'clientOrderId': None, 'timestamp': None, 'datetime': None, 'lastTradeTimestamp': None, 'lastUpdateTimestamp': None, 'symbol': 'CTK/USDT:USDT', 'type': None, 'timeInForce': None, 'postOnly': None, 'reduceOnly': None, 'side': None, 'price': None, 'triggerPrice': None, 'takeProfitPrice': None, 'stopLossPrice': None, 'amount': None, 'cost': None, 'average': None, 'filled': None, 'remaining': None, 'status': None, 'fee': None, 'trades': [], 'fees': [], 'stopPrice': None}
                cancel_result = await exchange.cancel_order(order_id, symbol, params={'category': 'linear'})
                result = await self.check_order_status(exchange, symbol, order_id)
                if result['status'] == 'canceled':
                    return result
            except Exception as e:
                error_data = json.loads(e.args[0][e.args[0].find("{"):])
                if 'order not exists or too late to cancel' in error_data['retMsg']:
                    result = await self.check_order_status(exchange, symbol, order_id)
                    if result['status'] == 'closed' or result['status'] == 'canceled':
                        return result
                else:
                    print(f"Bybit Cancel Order Exception: {e}")
                    return None
        print("safe_cancel_order")

    async def run(self):
        try:
            # 기존 run 로직
            while True:
                if self.status == "initialize":
                    await self.initialize()
                elif self.status == "enter_order":
                    await self.enter_order()
                elif self.status == "enter_order_monitor":
                    await self.enter_order_monitor()
                elif self.status == "exit_monitor":
                    await self.exit_monitor()
                elif self.status == "exit_order":
                    await self.exit_order()
                elif self.status == "exit_order_monitor":
                    await self.exit_order_monitor()
                elif self.status == "end":
                    await self.end()
                    break
        except Exception as e:
            print(f"Trader 실행 중 오류: {e}")
