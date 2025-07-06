from trader.base_trader import BaseTrader
import asyncio
import traceback
import time
from collections import deque
from datetime import datetime
import json
import aiofiles
from config_manager import ConfigManager


class TakerTakerTrader(BaseTrader):

    async def enter_order(self):
        current_spread = self.calculate_spread_percent()
        if not self.check_valid_spread():
            print(f"❌ [{self.symbol}] Spread {current_spread:.3f}% no longer valid. Ending trader.")
            self.status = "end"
            return None

        print(f"🎯 [{self.symbol}] Valid spread detected: {current_spread:.3f}% - Entering position...")
        check_enter_position: bool = await self.enter_position(self.symbol)
        if check_enter_position:
            print(f"✅ [{self.symbol}] Position entry successful - Starting order monitoring")
            self.status = "enter_order_monitor"
        else:
            print(f"❌ [{self.symbol}] Position entry failed - Ending trader")
            self.status = "end"
        return None

    async def enter_order_monitor(self):
        print(f"👀 [{self.symbol}] Starting order monitoring - Waiting for fills...")
        '''
        Bybit ccxt는 fetch_order가 안됨. -> fetch_open_order(id)로 조회하면 Open, Closed 상관없이 조회 가능
        {'info': {'symbol': 'BANANAS31USDT', 'orderType': 'Limit', 'orderLinkId': '', 'slLimitPrice': '0', 'orderId': 'db84d4a7-8800-4292-a027-abb8a08528c1', 'cancelType': 'UNKNOWN', 'avgPrice': '0.008805', 'stopOrderType': '', 'lastPriceOnCreated': '0.008806', 'orderStatus': 'Filled', 'createType': 'CreateByUser', 'takeProfit': '', 'cumExecValue': '9.6855', 'tpslMode': '', 'smpType': 'None', 'triggerDirection': '0', 'blockTradeId': '', 'isLeverage': '', 'rejectReason': 'EC_NoError', 'price': '0.008805', 'orderIv': '', 'createdTime': '1750991251841', 'tpTriggerBy': '', 'positionIdx': '0', 'timeInForce': 'GTC', 'leavesValue': '0', 'updatedTime': '1750991253554', 'side': 'Buy', 'smpGroup': '0', 'triggerPrice': '', 'tpLimitPrice': '0', 'cumExecFee': '0.0019371', 'leavesQty': '0', 'slTriggerBy': '', 'closeOnTrigger': False, 'placeType': '', 'cumExecQty': '1100', 'reduceOnly': False, 'qty': '1100', 'stopLoss': '', 'marketUnit': '', 'smpOrderId': '', 'triggerBy': '', 'nextPageCursor': 'db84d4a7-8800-4292-a027-abb8a08528c1%3A1750991251841%2Cdb84d4a7-8800-4292-a027-abb8a08528c1%3A1750991251841'}, 'id': 'db84d4a7-8800-4292-a027-abb8a08528c1', 'clientOrderId': None, 'timestamp': 1750991251841, 'datetime': '2025-06-27T02:27:31.841Z', 'lastTradeTimestamp': 1750991253554, 'lastUpdateTimestamp': 1750991253554, 'symbol': 'BANANAS31/USDT:USDT', 'type': 'limit', 'timeInForce': 'GTC', 'postOnly': False, 'reduceOnly': False, 'side': 'buy', 'price': 0.008805, 'triggerPrice': None, 'takeProfitPrice': None, 'stopLossPrice': None, 'amount': 1100.0, 'cost': 9.6855, 'average': 0.008805, 'filled': 1100.0, 'remaining': 0.0, 'status': 'closed', 'fee': {'cost': 0.0019371, 'currency': 'USDT'}, 'trades': [], 'fees': [{'cost': 0.0019371, 'currency': 'USDT'}], 'stopPrice': None}
        Binance ccxt는 fetch_order(id, symbol) 형태로 사용
        {'info': {'orderId': '33019363', 'symbol': 'HUSDT', 'status': 'FILLED', 'clientOrderId': 'x-cvBPrNm9e84c712a35a757ebc29168', 'price': '0.0187400', 'avgPrice': '0.0187500', 'origQty': '533', 'executedQty': '533', 'cumQuote': '9.9937500', 'timeInForce': 'GTC', 'type': 'LIMIT', 'reduceOnly': False, 'closePosition': False, 'side': 'SELL', 'positionSide': 'BOTH', 'stopPrice': '0.0000000', 'workingType': 'CONTRACT_PRICE', 'priceProtect': False, 'origType': 'LIMIT', 'priceMatch': 'NONE', 'selfTradePreventionMode': 'EXPIRE_MAKER', 'goodTillDate': '0', 'time': '1750988873962', 'updateTime': '1750988873962'}, 'id': '33019363', 'clientOrderId': 'x-cvBPrNm9e84c712a35a757ebc29168', 'timestamp': 1750988873962, 'datetime': '2025-06-27T01:47:53.962Z', 'lastTradeTimestamp': 1750988873962, 'lastUpdateTimestamp': 1750988873962, 'symbol': 'H/USDT:USDT', 'type': 'limit', 'timeInForce': 'GTC', 'postOnly': False, 'reduceOnly': False, 'side': 'sell', 'price': 0.01874, 'triggerPrice': None, 'amount': 533.0, 'cost': 9.99375, 'average': 0.01875, 'filled': 533.0, 'remaining': 0.0, 'status': 'closed', 'fee': None, 'trades': [], 'fees': [], 'stopPrice': None, 'takeProfitPrice': None, 'stopLossPrice': None}
        '''

        max_enter_order_time = self.config_manager.getfloat('TRADER', 'max_enter_order_time')
        start_time = time.time()
        k = 0
        while time.time() - start_time < max_enter_order_time:
            long_order_check = self.check_order_status(
                self.enter_order_result["long_exchange"],
                self.enter_order_result["long_symbol"],
                self.enter_order_result["long_order_id"]
            )
            short_order_check = self.check_order_status(
                self.enter_order_result["short_exchange"],
                self.enter_order_result["short_symbol"],
                self.enter_order_result["short_order_id"]
            )
            long_order_result, short_order_result = await asyncio.gather(long_order_check, short_order_check)

            # 체결 안된 수량이 min_qty 이하로 남아 있으면 취소 후 재주문이 불가능
            long_min_qty = self.calculate_min_qty(exchange=self.enter_order_result["long_exchange"], symbol=self.enter_order_result["long_symbol"], price=float(long_order_result['price']))
            short_min_qty = self.calculate_min_qty(exchange=self.enter_order_result["short_exchange"], symbol=self.enter_order_result["short_symbol"], price=float(short_order_result['price']))

            print_interval = 10
            k += 0
            if k % int(print_interval / 0.5) == 1:
            # if (time.time() - start_time)%30 < 1:
                elapsed_time = int(time.time() - start_time)
                current_spread = self.get_lastest_data()['spread_pct']

                print(f"\n📊 [{self.symbol}] ORDER MONITORING STATUS (T+{elapsed_time}s)")
                print(f"📈 Current Spread: {current_spread:+.3f}%")

                # Long order status
                long_fill_pct = (long_order_result['filled'] / long_order_result['amount']) * 100
                long_status = "✅ FILLED" if long_order_result['filled'] == long_order_result['amount'] else f"⏳ {long_fill_pct:.1f}%"
                print(f"🟢 Long  ({self.enter_order_result['long_exchange'].id.upper()}): {long_order_result['filled']:.0f}/{long_order_result['amount']:.0f} @ ${long_order_result['average']:.6f} | {long_status}")

                # Short order status  
                short_fill_pct = (short_order_result['filled'] / short_order_result['amount']) * 100
                short_status = "✅ FILLED" if short_order_result['filled'] == short_order_result['amount'] else f"⏳ {short_fill_pct:.1f}%"
                print(f"🔴 Short ({self.enter_order_result['short_exchange'].id.upper()}): {short_order_result['filled']:.0f}/{short_order_result['amount']:.0f} @ ${short_order_result['average']:.6f} | {short_status}")
                print("-" * 60)

            # noinspection PyTypeChecker
            if (long_order_result['filled'] >= self.enter_order_result["long_qty"] - long_min_qty) and (short_order_result['filled'] >= self.enter_order_result["short_qty"] - short_min_qty):
                print(f"🎉 [{self.symbol}] Both orders successfully filled! Moving to exit monitoring...")
                self.status = "exit_monitor"
                long_cancel_result, short_cancel_result = await asyncio.gather(
                    self.safe_cancel_order(self.enter_order_result["long_exchange"],
                                           self.enter_order_result["long_symbol"],
                                           self.enter_order_result["long_order_id"]),
                    self.safe_cancel_order(self.enter_order_result["short_exchange"],
                                           self.enter_order_result["short_symbol"],
                                           self.enter_order_result["short_order_id"]))

                self.append_long_short_order_result(long_order_result=long_cancel_result,
                                                    short_order_result=short_cancel_result)

                self.calculate_info_order_result()

                return None

            await asyncio.sleep(0.5)

        # 미체결된 주문 일괄 취소
        long_cancel_result, short_cancel_result = await asyncio.gather(self.safe_cancel_order(self.enter_order_result["long_exchange"], self.enter_order_result["long_symbol"], self.enter_order_result["long_order_id"]),
                                                                       self.safe_cancel_order(self.enter_order_result["short_exchange"], self.enter_order_result["short_symbol"], self.enter_order_result["short_order_id"]))

        self.append_long_short_order_result(long_order_result=long_cancel_result,
                                            short_order_result=short_cancel_result)

        long_min_qty = self.calculate_min_qty(exchange=self.enter_order_result["long_exchange"],
                                              symbol=self.enter_order_result["long_symbol"],
                                              price=float(long_cancel_result['price']))
        short_min_qty = self.calculate_min_qty(exchange=self.enter_order_result["short_exchange"],
                                               symbol=self.enter_order_result["short_symbol"],
                                               price=float(short_cancel_result['price']))

        sell_taker_price_margin = self.config_manager.getfloat('TRADER', 'sell_taker_price_margin')
        buy_taker_price_margin = self.config_manager.getfloat('TRADER', 'buy_taker_price_margin')

        # Case 1. 미체결 / 미체결 -> End
        if long_cancel_result['filled'] == 0 and short_cancel_result['filled'] == 0:
            print(f"❌ [{self.symbol}] CASE 1: No fills on either exchange - Ending trade")
            print(f"   🟢 {self.enter_order_result['long_exchange'].id.upper()}: 0/{long_cancel_result['amount']:.0f} filled")
            print(f"   🔴 {self.enter_order_result['short_exchange'].id.upper()}: 0/{short_cancel_result['amount']:.0f} filled")
            self.calculate_info_order_result()
            self.status = "end"
            return None

        # Case 2. 최소수량 이하 미체결 / 최소수량 이하 미체결 -> 최소 수량 추가 거래
        if long_cancel_result['filled'] < long_min_qty and short_cancel_result['filled'] < short_min_qty:
            print(f"⚠️  [{self.symbol}] CASE 2: Both fills below minimum quantity - Attempting additional trades")
            print(f"   🟢 {self.enter_order_result['long_exchange'].id.upper()}: {long_cancel_result['filled']:.0f}/{long_cancel_result['amount']:.0f} filled (min: {long_min_qty:.0f})")
            print(f"   🔴 {self.enter_order_result['short_exchange'].id.upper()}: {short_cancel_result['filled']:.0f}/{short_cancel_result['amount']:.0f} filled (min: {short_min_qty:.0f})")

            short_adjusted_remain_qty = self.make_qty_step(
                market=self.enter_order_result['short_exchange'].markets[self.enter_order_result['short_symbol']],
                qty=short_min_qty,
                adjust_type='ceil')
            long_adjusted_remain_qty = self.make_qty_step(
                market=self.enter_order_result['long_exchange'].markets[self.enter_order_result['long_symbol']],
                qty=long_min_qty,
                adjust_type='ceil')

            short_adjusted_price = float(short_cancel_result['price']) * sell_taker_price_margin
            long_adjusted_price = float(long_cancel_result['price']) * buy_taker_price_margin

            short_order_result = await self.enter_order_result['short_exchange'].create_limit_sell_order(self.enter_order_result['short_symbol'], short_adjusted_remain_qty, short_adjusted_price)
            long_order_result = await self.enter_order_result['long_exchange'].create_limit_buy_order(self.enter_order_result['long_symbol'], long_adjusted_remain_qty, long_adjusted_price)

            max_taker_enter_order_time = self.config_manager.getfloat('TRADER', 'max_taker_enter_order_time')
            start_time = time.time()
            while time.time() - start_time < max_taker_enter_order_time:
                short_order_result = await self.check_order_status(
                    self.enter_order_result["short_exchange"],
                    self.enter_order_result["short_symbol"],
                    short_order_result['id']
                )
                long_order_result = await self.check_order_status(
                    self.enter_order_result["long_exchange"],
                    self.enter_order_result["long_symbol"],
                    long_order_result['id']
                )
                if long_order_result['status'] == 'closed' and short_order_result['status'] == 'closed':
                    break
                await asyncio.sleep(0.1)
            else:
                if long_order_result['status'] != 'closed':
                    additional_long_order = await self.enter_order_result['long_exchange'].create_market_buy_order(self.enter_order_result['long_symbol'], long_adjusted_remain_qty)
                    self.append_long_short_order_result(long_order_result=additional_long_order)
                elif short_order_result['status'] != 'closed':
                    additional_short_order = await self.enter_order_result['short_exchange'].create_market_sell_order(self.enter_order_result['short_symbol'], short_adjusted_remain_qty)
                    self.append_long_short_order_result(short_order_result=additional_short_order)

            self.append_long_short_order_result(long_order_result=long_order_result,
                                                short_order_result=short_order_result)

            self.calculate_info_order_result()

            self.status = "exit_monitor"
            return None

        # Case 3. 전체 체결 / 미체결 or 일부 체결 -> 미체결 or 일부 체결 쪽 남은 수량만큼 지정시장가
        if (long_cancel_result['filled'] >= self.enter_order_result["long_qty"] - long_min_qty) and (short_cancel_result['filled'] <= self.enter_order_result["short_qty"] - short_min_qty):
            # Short 추가 거래
            print(f"[{self.symbol}] Case 3-1. (전체 체결 / 미체결 or 일부 체결) Short 추가 거래")
            print(f"[{self.symbol}] {self.enter_order_result['long_exchange'].id} Filled ({long_cancel_result['filled']} / {long_cancel_result['amount']})")
            print(f"[{self.symbol}] {self.enter_order_result['short_exchange'].id} Filled ({short_cancel_result['filled']} / {short_cancel_result['amount']})")

            remain_qty = self.enter_order_result["short_qty"] - short_cancel_result['filled']
            adjusted_remain_qty = self.make_qty_step(
                market=self.enter_order_result['short_exchange'].markets[self.enter_order_result['short_symbol']],
                qty=remain_qty,
                adjust_type='round')

            adjusted_price = float(short_cancel_result['price']) * sell_taker_price_margin

            short_order_result = await self.enter_order_result['short_exchange'].create_limit_sell_order(self.enter_order_result['short_symbol'], adjusted_remain_qty, adjusted_price)

            max_taker_enter_order_time = self.config_manager.getfloat('TRADER', 'max_taker_enter_order_time')
            start_time = time.time()
            while time.time() - start_time < max_taker_enter_order_time:
                short_order_result = await self.check_order_status(
                    self.enter_order_result["short_exchange"],
                    self.enter_order_result["short_symbol"],
                    short_order_result['id']
                )
                if short_order_result['status'] == 'closed':
                    break
                await asyncio.sleep(0.1)
            else:
                if short_order_result['status'] != 'closed':
                    remain_qty = adjusted_remain_qty - short_order_result['filled']
                    adjusted_remain_qty = self.make_qty_step(
                        market=self.enter_order_result['short_exchange'].markets[self.enter_order_result['short_symbol']],
                        qty=remain_qty,
                        adjust_type='round')
                    additional_short_order = await self.enter_order_result['short_exchange'].create_market_sell_order(self.enter_order_result['short_symbol'], adjusted_remain_qty)
                    self.append_long_short_order_result(long_order_result=None,
                                                        short_order_result=additional_short_order)

            self.append_long_short_order_result(long_order_result=None,
                                                short_order_result=short_order_result)

            self.calculate_info_order_result()

            self.status = "exit_monitor"
            return None
        if (long_cancel_result['filled'] <= self.enter_order_result["long_qty"] - long_min_qty) and (short_cancel_result['filled'] >= self.enter_order_result["short_qty"] - short_min_qty):
            # Long 추가 거래
            print(f"[{self.symbol}] Case 3-2. (전체 체결 / 미체결 or 일부 체결) Long 추가 거래")
            print(f"[{self.symbol}] {self.enter_order_result['long_exchange'].id} Filled ({long_cancel_result['filled']} / {long_cancel_result['amount']})")
            print(f"[{self.symbol}] {self.enter_order_result['short_exchange'].id} Filled ({short_cancel_result['filled']} / {short_cancel_result['amount']})")

            remain_qty = self.enter_order_result["long_qty"] - long_cancel_result['filled']
            adjusted_remain_qty = self.make_qty_step(
                market=self.enter_order_result['long_exchange'].markets[self.enter_order_result['long_symbol']],
                qty=remain_qty,
                adjust_type='round')

            adjusted_price = float(long_cancel_result['price']) * buy_taker_price_margin

            long_order_result = await self.enter_order_result['long_exchange'].create_limit_buy_order(self.enter_order_result['long_symbol'], adjusted_remain_qty, adjusted_price)

            max_taker_enter_order_time = self.config_manager.getfloat('TRADER', 'max_taker_enter_order_time')
            start_time = time.time()
            while time.time() - start_time < max_taker_enter_order_time:
                long_order_result = await self.check_order_status(
                    self.enter_order_result["long_exchange"],
                    self.enter_order_result["long_symbol"],
                    long_order_result['id']
                )
                if long_order_result['status'] == 'closed':
                    break
                await asyncio.sleep(0.1)
            else:
                if long_order_result['status'] != 'closed':
                    remain_qty = adjusted_remain_qty - long_order_result['filled']
                    adjusted_remain_qty = self.make_qty_step(
                        market=self.enter_order_result['long_exchange'].markets[self.enter_order_result['long_symbol']],
                        qty=remain_qty,
                        adjust_type='round')
                    additional_long_order = await self.enter_order_result['long_exchange'].create_market_sell_order(self.enter_order_result['long_symbol'], adjusted_remain_qty)
                    self.append_long_short_order_result(long_order_result=additional_long_order,
                                                        short_order_result=None)

            self.append_long_short_order_result(long_order_result=long_order_result,
                                                short_order_result=None)

            self.calculate_info_order_result()

            self.status = "exit_monitor"
            return None

        # Case 4. 일부 체결 / 미체결 or 일부 체결 -> 미체결 or 일부 체결 쪽 수량 맞추기 위한 지정시장가
        filled_ratio_threshold = 0.03
        if (long_cancel_result['filled'] <= self.enter_order_result["long_qty"] - long_min_qty) and (short_cancel_result['filled'] <= self.enter_order_result["short_qty"] - short_min_qty):
            if abs((long_cancel_result['filled'] / long_cancel_result['amount']) - (short_cancel_result['filled'] / short_cancel_result['amount'])) < filled_ratio_threshold:
                print(f"[{self.symbol}] Case 4-1. (일부 체결 / 미체결 or 일부 체결) 차이 < Threshold -> Skip")
                print(f"[{self.symbol}] {self.enter_order_result['long_exchange'].id} Filled ({long_cancel_result['filled']} / {long_cancel_result['amount']})")
                print(f"[{self.symbol}] {self.enter_order_result['short_exchange'].id} Filled ({short_cancel_result['filled']} / {short_cancel_result['amount']})")

                self.calculate_info_order_result()

                self.status = "exit_monitor"
                return None
            if (long_cancel_result['filled'] / long_cancel_result['amount']) > (short_cancel_result['filled'] / short_cancel_result['amount']):
                # Short 추가 거래
                print(f"[{self.symbol}] Case 4-2. (일부 체결 / 미체결 or 일부 체결) Short 추가 거래")
                print(f"[{self.symbol}] {self.enter_order_result['long_exchange'].id} Filled ({long_cancel_result['filled']} / {long_cancel_result['amount']})")
                print(f"[{self.symbol}] {self.enter_order_result['short_exchange'].id} Filled ({short_cancel_result['filled']} / {short_cancel_result['amount']})")

                remain_qty = short_cancel_result['amount'] * ((long_cancel_result['filled'] / long_cancel_result['amount']) - (short_cancel_result['filled'] / short_cancel_result['amount']))
                if remain_qty < short_min_qty:
                    remain_qty = short_min_qty
                adjusted_remain_qty = self.make_qty_step(
                    market=self.enter_order_result['short_exchange'].markets[self.enter_order_result['short_symbol']],
                    qty=remain_qty,
                    adjust_type='round')

                adjusted_price = float(short_cancel_result['price']) * sell_taker_price_margin
                short_order_result = await self.enter_order_result['short_exchange'].create_limit_sell_order(self.enter_order_result['short_symbol'], adjusted_remain_qty, adjusted_price)

                max_taker_enter_order_time = self.config_manager.getfloat('TRADER', 'max_taker_enter_order_time')
                start_time = time.time()
                while time.time() - start_time < max_taker_enter_order_time:
                    short_order_result = await self.check_order_status(
                        self.enter_order_result["short_exchange"],
                        self.enter_order_result["short_symbol"],
                        short_order_result['id']
                    )
                    if short_order_result['status'] == 'closed':
                        break
                    await asyncio.sleep(0.1)
                else:
                    if short_order_result['status'] != 'closed':
                        remain_qty = adjusted_remain_qty - short_order_result['filled']
                        adjusted_remain_qty = self.make_qty_step(
                            market=self.enter_order_result['short_exchange'].markets[self.enter_order_result['short_symbol']],
                            qty=remain_qty,
                            adjust_type='round')
                        additional_short_order = await self.enter_order_result[
                            'short_exchange'].create_market_sell_order(self.enter_order_result['short_symbol'],
                                                                       adjusted_remain_qty)
                        self.append_long_short_order_result(long_order_result=None,
                                                            short_order_result=additional_short_order)


                self.append_long_short_order_result(long_order_result=None,
                                                    short_order_result=short_order_result)

                self.calculate_info_order_result()

                self.status = "exit_monitor"
                return None
            if (long_cancel_result['filled'] / long_cancel_result['amount']) < (short_cancel_result['filled'] / short_cancel_result['amount']):
                # Long 추가 거래
                print(f"[{self.symbol}] Case 4-3. (일부 체결 / 미체결 or 일부 체결) Long 추가 거래")
                print(f"[{self.symbol}] {self.enter_order_result['long_exchange'].id} Filled ({long_cancel_result['filled']} / {long_cancel_result['amount']})")
                print(f"[{self.symbol}] {self.enter_order_result['short_exchange'].id} Filled ({short_cancel_result['filled']} / {short_cancel_result['amount']})")

                remain_qty = long_cancel_result['amount'] * ((short_cancel_result['filled'] / short_cancel_result['amount']) - (long_cancel_result['filled'] / long_cancel_result['amount']))
                if remain_qty < long_min_qty:
                    remain_qty = long_min_qty
                adjusted_remain_qty = self.make_qty_step(
                    market=self.enter_order_result['short_exchange'].markets[self.enter_order_result['short_symbol']],
                    qty=remain_qty,
                    adjust_type='round')

                adjusted_price = float(long_cancel_result['price']) * buy_taker_price_margin
                long_order_result = await self.enter_order_result['long_exchange'].create_limit_buy_order(self.enter_order_result['long_symbol'], adjusted_remain_qty, adjusted_price)
                max_taker_enter_order_time = self.config_manager.getfloat('TRADER', 'max_taker_enter_order_time')
                start_time = time.time()
                while time.time() - start_time < max_taker_enter_order_time:
                    long_order_result = await self.check_order_status(
                        self.enter_order_result["long_exchange"],
                        self.enter_order_result["long_symbol"],
                        long_order_result['id']
                    )
                    if long_order_result['status'] == 'closed':
                        break
                    await asyncio.sleep(0.1)
                else:
                    if long_order_result['status'] != 'closed':
                        remain_qty = adjusted_remain_qty - long_order_result['filled']
                        adjusted_remain_qty = self.make_qty_step(
                            market=self.enter_order_result['long_exchange'].markets[self.enter_order_result['long_symbol']],
                            qty=remain_qty,
                            adjust_type='round')
                        additional_long_order = await self.enter_order_result['long_exchange'].create_market_sell_order(
                            self.enter_order_result['long_symbol'], adjusted_remain_qty)
                        self.append_long_short_order_result(long_order_result=additional_long_order,
                                                            short_order_result=None)

                self.append_long_short_order_result(long_order_result=long_order_result,
                                                    short_order_result=None)

                self.calculate_info_order_result()

                self.status = "exit_monitor"
                return None
        return None

    async def exit_monitor(self):
        entry_spread = self.enter_order_monitor_result['info']['entry_spread_signed']
        direction_str = "🟢 LONG BINANCE/SHORT BYBIT" if self.direction else "🔴 SHORT BINANCE/LONG BYBIT"
        print(f"🎯 [{self.symbol}] Starting exit monitoring | Entry spread: {entry_spread:+.3f}% | Direction: {direction_str}")
        stop_loss_percent: float = self.config_manager.getfloat('TRADER', 'stop_loss_percent')
        take_profit_percent: float = self.config_manager.getfloat('TRADER', 'take_profit_percent')
        max_exit_deque_len: int = self.config_manager.getint('TRADER', 'max_exit_deque_len')
        max_exit_monitor_time: float = self.config_manager.getfloat('TRADER', 'max_exit_monitor_time')
        exit_monitor_interval: float = self.config_manager.getfloat('TRADER', 'exit_monitor_interval')
        count_dict = {"stop_loss": deque(maxlen=max_exit_deque_len), "take_profit": deque(maxlen=max_exit_deque_len)}
        strat_time = time.time()

        print_interval = 30
        k = 0
        while time.time() - strat_time < max_exit_monitor_time:
            k += 1
            if k % int(print_interval/exit_monitor_interval) == 1:
                current_spread = self.get_lastest_data()['spread_pct']
                entry_spread = self.enter_order_monitor_result['info']['entry_spread_signed']
                spread_change = current_spread - entry_spread
                elapsed_time = int(time.time() - strat_time)

                print(f"📊 [{self.symbol}] EXIT MONITORING (T+{elapsed_time}s)")
                print(f"   📈 Entry Spread: {entry_spread:+.3f}% | Current: {current_spread:+.3f}% | Change: {spread_change:+.3f}%")
                print(f"   🎯 Stop Loss: {-stop_loss_percent:.3f}% | Take Profit: {take_profit_percent:.3f}%")
            # spread_sign = self.enter_monitor_result['entry_spread_signed']/abs(self.enter_monitor_result['entry_spread_signed'])
            if not self.direction:
                current_data = self.get_lastest_data()
                if self.enter_order_monitor_result['info']['entry_spread_signed'] >= 0:
                    self.status = "exit_order"
                    print(f"❌ [{self.symbol}] WRONG ENTRY SPREAD - Expected negative, got {self.enter_order_monitor_result['info']['entry_spread_signed']:+.3f}%")
                    self.append_exit_monitor_result(current_data, exit_type='wrong_entry')
                    return None
                # current_data['spread_pct']: 부호 있음 / self.enter_order_monitor_result['info']['entry_spread']: 절대값
                stop_loss_condition = current_data['spread_pct'] - self.enter_order_monitor_result['info']['entry_spread_signed'] <  -stop_loss_percent
                take_profit_condition = (current_data['spread_pct'] - self.enter_order_result['entry_spread_signed'] > take_profit_percent) or (current_data['spread_pct'] >= 0)
                count_dict["stop_loss"].append(stop_loss_condition)
                count_dict["take_profit"].append(take_profit_condition)
                if all(count_dict["stop_loss"]):
                    self.status = "exit_order"
                    spread_change = current_data['spread_pct'] - self.enter_order_monitor_result['info']['entry_spread_signed']
                    print(f"🛑 [{self.symbol}] STOP LOSS TRIGGERED - Spread change: {spread_change:+.3f}% (threshold: {-stop_loss_percent:.3f}%)")
                    self.append_exit_monitor_result(current_data, exit_type='stop_loss')
                    return None
                elif all(count_dict["take_profit"]):
                    self.status = "exit_order"
                    spread_change = current_data['spread_pct'] - self.enter_order_monitor_result['info']['entry_spread_signed']
                    print(f"💰 [{self.symbol}] TAKE PROFIT TRIGGERED - Spread change: {spread_change:+.3f}% (threshold: {take_profit_percent:.3f}%)")
                    self.append_exit_monitor_result(current_data, exit_type='take_profit')
                    return None
            else:
                current_data = self.get_lastest_data()
                if self.enter_order_monitor_result['info']['entry_spread_signed'] <= 0:
                    self.status = "exit_order"
                    print(f"❌ [{self.symbol}] WRONG ENTRY SPREAD - Expected positive, got {self.enter_order_monitor_result['info']['entry_spread_signed']:+.3f}%")
                    self.append_exit_monitor_result(current_data, exit_type='wrong_entry')
                    return None
                stop_loss_condition = current_data['spread_pct'] - self.enter_order_monitor_result['info']['entry_spread_signed'] > stop_loss_percent
                take_profit_condition = (current_data['spread_pct'] - self.enter_order_result['entry_spread_signed'] > take_profit_percent) or (current_data['spread_pct'] <= 0)
                count_dict["stop_loss"].append(stop_loss_condition)
                count_dict["take_profit"].append(take_profit_condition)
                if all(count_dict["stop_loss"]):
                    self.status = "exit_order"
                    spread_change = current_data['spread_pct'] - self.enter_order_monitor_result['info']['entry_spread_signed']
                    print(f"🛑 [{self.symbol}] STOP LOSS TRIGGERED - Spread change: {spread_change:+.3f}% (threshold: {stop_loss_percent:.3f}%)")
                    self.append_exit_monitor_result(current_data, exit_type='stop_loss')
                    return None
                elif all(count_dict["take_profit"]):
                    self.status = "exit_order"
                    spread_change = current_data['spread_pct'] - self.enter_order_monitor_result['info']['entry_spread_signed']
                    print(f"💰 [{self.symbol}] TAKE PROFIT TRIGGERED - Spread change: {spread_change:+.3f}% (threshold: {take_profit_percent:.3f}%)")
                    self.append_exit_monitor_result(current_data, exit_type='take_profit')
                    return None
            await asyncio.sleep(exit_monitor_interval)
        self.status = "exit_order"
        elapsed_time = int(time.time() - strat_time)
        print(f"⏰ [{self.symbol}] EXIT TIMEOUT - Maximum monitoring time ({max_exit_monitor_time:.0f}s) exceeded after {elapsed_time}s")
        current_data = self.get_lastest_data()
        self.append_exit_monitor_result(current_data, exit_type='time_out')
        return None

    async def exit_order(self):
        # Todo: exit_type에 따라 바로 청산할지, 현재 spread를 확인하면서 할지 추가
        exit_type = self.exit_monitor_result.get('exit_type', 'unknown')
        current_spread = self.get_lastest_data()['spread_pct']
        print(f"🔄 [{self.symbol}] CLOSING POSITIONS - Reason: {exit_type.upper()} | Current spread: {current_spread:+.3f}%")

        lower_exchange = self.exit_monitor_result['long_exchange']
        higher_exchange = self.exit_monitor_result['short_exchange']

        lower_symbol = self.exit_monitor_result['long_symbol']
        higher_symbol = self.exit_monitor_result['short_symbol']

        lower_qty = self.exit_monitor_result['long_qty']
        higher_qty = self.exit_monitor_result['short_qty']

        # 청산 -> Long은 sell, Short은 buy
        sell_taker_price_margin = self.config_manager.getfloat('TRADER', 'sell_taker_price_margin')
        buy_taker_price_margin = self.config_manager.getfloat('TRADER', 'buy_taker_price_margin')

        current_data = self.get_lastest_data()
        lower_price = current_data[f'{lower_exchange.id}_price']
        higher_price = current_data[f'{higher_exchange.id}_price']
        sell_price = lower_price * sell_taker_price_margin
        buy_price = higher_price * buy_taker_price_margin

        bybit_params = {'category': 'linear'}

        long_params = bybit_params if lower_exchange.id == 'bybit' else {}
        short_params = bybit_params if higher_exchange.id == 'bybit' else {}

        # Todo: 주문 실패 시, 방어 로직 필요
        long_order_co = lower_exchange.create_limit_sell_order(lower_symbol, lower_qty, sell_price, params=long_params)
        short_order_co = higher_exchange.create_limit_buy_order(higher_symbol, higher_qty, buy_price, params=short_params)
        long_order, short_order = await asyncio.gather(long_order_co, short_order_co)

        self.exit_order_result = {
            "long_exchange": lower_exchange,
            "short_exchange": higher_exchange,
            "long_symbol": lower_symbol,
            "short_symbol": higher_symbol,
            "long_qty": lower_qty,
            "long_price": lower_price,
            "long_order_id": long_order['id'],
            "short_qty": higher_qty,
            "short_price": higher_price,
            "short_order_id": short_order['id'],
            "exit_spread": abs(current_data['spread_pct']),
            "exit_spread_signed": current_data['spread_pct'],
            "timestamp": time.time()
        }

        self.status = "exit_order_monitor"

        await asyncio.sleep(10)

    async def exit_order_monitor(self):
        print(f"Exit Order Monitoring {self.symbol} trader")
        print(f"[{self.symbol}] exit_spread: {self.exit_order_result['exit_spread']}")

        long_exchange = self.exit_order_result['long_exchange']
        long_symbol = self.exit_order_result['long_symbol']
        long_order_id = self.exit_order_result['long_order_id']
        long_result = await self.check_order_status(long_exchange, long_symbol, long_order_id)
        print(f"[{self.symbol}] Long {long_exchange.id} order status: {long_result['filled']} / {long_result['average']}")

        short_exchange = self.exit_order_result['short_exchange']
        short_symbol = self.exit_order_result['short_symbol']
        short_order_id = self.exit_order_result['short_order_id']
        short_result = await self.check_order_status(short_exchange, short_symbol, short_order_id)
        print(f"[{self.symbol}] Short {short_exchange.id} order status: {short_result['filled']} / {short_result['average']}")

        long_profit = (long_result['average'] - self.enter_order_monitor_result['info']['long_price_average']) * self.enter_order_monitor_result['info']['long_qty']
        short_profit = -1 * (short_result['average'] - self.enter_order_monitor_result['info']['short_price_average']) * self.enter_order_monitor_result['info']['short_qty']

        long_profit = long_profit - (0.05 / 100) * ((long_result['average'] + self.enter_order_monitor_result['info']['long_price_average']) * self.enter_order_monitor_result['info']['long_qty'])
        short_profit = short_profit - (0.05 / 100) * ((short_result['average'] + self.enter_order_monitor_result['info']['short_price_average']) * self.enter_order_monitor_result['info']['short_qty'])

        trade_result = {
            'timenow': str(datetime.now()),
            'long_exchange': long_exchange.id,
            'long_symbol': long_symbol,
            'short_exchange': short_exchange.id,
            'short_symbol': short_symbol,
            'direction': self.direction,
            'long_signal_entry_price': self.enter_order_result['long_price'],
            'long_signal_entry_qty': self.enter_order_result['long_qty'],
            'short_signal_entry_price': self.enter_order_result['short_price'],
            'short_signal_entry_qty': self.enter_order_result['short_qty'],
            'entry_signal_spread': self.enter_order_result['entry_spread_signed'],
            'long_entry_price': self.enter_order_monitor_result['info']['long_price_average'],
            'long_entry_qty': self.enter_order_monitor_result['info']['long_qty'],
            'short_entry_price': self.enter_order_monitor_result['info']['short_price_average'],
            'short_entry_qty': self.enter_order_monitor_result['info']['short_qty'],
            'entry_spread': self.enter_order_monitor_result['info']['entry_spread_signed'],
            'long_signal_exit_price': self.exit_order_result['long_price'],
            'short_signal_exit_price': self.exit_order_result['short_price'],
            'exit_signal_spread': self.exit_order_result['exit_spread_signed'],
            'long_exit_price': long_result['average'],
            'short_exit_price': short_result['average'],
            'exit_spread': 100 * (long_result['average'] - short_result['average']) / min(long_result['average'], short_result['average']),
            'long_profit': long_profit,
            'short_profit': short_profit,
            'total_profit': long_profit + short_profit,
        }

        async with aiofiles.open('./result.txt', mode='a+') as f:
            await f.write(json.dumps(trade_result, ensure_ascii=False) + '\n')

        self.status = 'end'
        await asyncio.sleep(1)

    async def enter_position(self, symbol):
        if self.direction:
            higher_exchange, lower_exchange = (self.binance, self.bybit)
        else:
            higher_exchange, lower_exchange = (self.bybit, self.binance)

        base_currency = 'USDT'

        lower_symbol = symbol.split(base_currency)[0] + "/" + base_currency + f":{base_currency}"
        higher_symbol = symbol.split(base_currency)[0] + "/" + base_currency + f":{base_currency}"

        if not lower_symbol or not higher_symbol:
            print(f"⛔️ 유효하지 않은 심볼 → 건너뜀: {symbol}")
            return False

        try:
            await asyncio.gather(self.safe_set_margin_mode(lower_exchange, lower_symbol, 'isolated'),
                                 self.safe_set_margin_mode(higher_exchange, higher_symbol, 'isolated'))

            await asyncio.gather(self.safe_set_leverage(lower_exchange, lower_symbol, 1),
                                 self.safe_set_leverage(higher_exchange, higher_symbol, 1))

            print(datetime.now())
            lastest_data = self.get_lastest_data()

            if self.direction:
                higher_price, lower_price = lastest_data['binance_price'], lastest_data['bybit_price']
            else:
                higher_price, lower_price = lastest_data['bybit_price'], lastest_data['binance_price']

            lower_qty = await self.calculate_qty_for_fixed_usdt(lower_exchange, lower_symbol, lower_price, self.target_usdt)
            higher_qty = await self.calculate_qty_for_fixed_usdt(higher_exchange, higher_symbol, higher_price, self.target_usdt)

            # 거래소 간 qty 기준으로 인해 spread 대비 qty 수량 차이가 훨씬 클 경우 거래 x
            if abs(higher_qty - lower_qty) / min(higher_qty, lower_qty) > abs(higher_price - lower_price) / min(higher_price, lower_price) * 5:
                print(f"[{self.symbol}] Difference of qty is too large. Ending trader.")
                return False

            if not self.check_valid_spread():
                print(f"[{self.symbol}] No more valid spreads. Ending trader.")
                return False

            enter_buy_price_margin = self.config_manager.getfloat('TRADER', 'enter_buy_price_margin')
            enter_sell_price_margin = self.config_manager.getfloat('TRADER', 'enter_sell_price_margin')

            buy_price = lower_price * enter_buy_price_margin
            sell_price = higher_price * enter_sell_price_margin

            usdt_required = self.target_usdt * self.config_manager.getfloat('TRADER', 'usdt_required_multiplier')

            lower_balance = await self.check_balance(lower_exchange)
            higher_balance = await self.check_balance(higher_exchange)

            # Todo: 잔고 부족 시, 있는 수준으로만?
            if lower_balance < usdt_required or higher_balance < usdt_required:
                print(f"⛔️ 잔고 부족 → 건너뜀: {symbol}")
                print(f"   ↳ 필요 USDT: {usdt_required:.2f}")
                print(f"   ↳ {lower_exchange.id} 잔고: {lower_balance:.4f} USDT")
                print(f"   ↳ {higher_exchange.id} 잔고: {higher_balance:.4f} USDT")
                return False

            print("=" * 60)
            print(f"🚀 진입 시도: {symbol}")
            print(f"롱: {lower_exchange.id} - {lower_qty} | 숏: {higher_exchange.id} - {higher_qty}")
            print(f"가격: B={lastest_data['binance_price']}, Y={lastest_data['bybit_price']} | 스프레드={lastest_data['spread_pct']:+.2f}%")

            bybit_params = {'category': 'linear'}

            long_params = bybit_params if lower_exchange.id == 'bybit' else {}
            short_params = bybit_params if higher_exchange.id == 'bybit' else {}

            # Todo: 주문 실패 시, 방어 로직 필요
            long_order_co = lower_exchange.create_limit_buy_order(lower_symbol, lower_qty, buy_price, params=long_params)
            short_order_co = higher_exchange.create_limit_sell_order(higher_symbol, higher_qty, sell_price, params=short_params)
            long_order, short_order = await asyncio.gather(long_order_co, short_order_co)

            # ✅ 체결 대기용으로 pending_orders에 저장
            self.enter_order_result = {
                "long_exchange": lower_exchange,
                "short_exchange": higher_exchange,
                "long_symbol": lower_symbol,
                "short_symbol": higher_symbol,
                "long_qty": lower_qty,
                "long_price": lower_price,
                "long_order_id": long_order['id'],
                "short_qty": higher_qty,
                "short_price": higher_price,
                "short_order_id": short_order['id'],
                "entry_spread": abs(lastest_data['spread_pct']),
                "entry_spread_signed": lastest_data['spread_pct'],
                "timestamp": time.time()
            }

            print(f"⏳ 지정가 주문 완료 → 체결 대기 중 (symbol: {symbol})")
            print("=" * 60 + "\n")

            return True

        except Exception as e:
            print(f"❌ 진입 실패: {e}")
            traceback.print_exc()
            return False

    def append_long_short_order_result(self, long_order_result=None, short_order_result=None):
        if long_order_result is not None:
            self.enter_order_monitor_result['long'].append({"exchange": self.enter_order_result["long_exchange"],
                                                    "symbol": self.enter_order_result["long_symbol"],
                                                    "qty": long_order_result["filled"],
                                                    "price": long_order_result["average"],
                                                    "order_id": long_order_result['id'],
                                                    "cost": long_order_result['cost']})
        if short_order_result is not None:
            self.enter_order_monitor_result['short'].append({"exchange": self.enter_order_result["short_exchange"],
                                                     "symbol": self.enter_order_result["short_symbol"],
                                                     "qty": short_order_result["filled"],
                                                     "price": short_order_result["average"],
                                                     "order_id": short_order_result['id'],
                                                     "cost": short_order_result['cost']})

    def calculate_info_order_result(self):
        long_price_average, short_price_average = self.calculate_average_price(self.enter_order_monitor_result['long'], self.enter_order_monitor_result['short'])
        long_qty, short_qty = self.calculate_sum_qty(self.enter_order_monitor_result['long'], self.enter_order_monitor_result['short'])
        # short_cost_list = [x['cost'] for x in self.enter_order_monitor_result['short'] if x['price'] is not None]
        # long_cost_list = [x['cost'] for x in self.enter_order_monitor_result['long'] if x['price'] is not None]
        # short_qty_list = [x['qty'] for x in self.enter_order_monitor_result['short']]
        # long_qty_list = [x['qty'] for x in self.enter_order_monitor_result['long']]
        # short_price_average = sum(short_cost_list) / sum(short_qty_list)
        # long_price_average = sum(long_cost_list) / sum(long_qty_list)
        real_entry_spread_pct = 100 * (short_price_average - long_price_average) / min(short_price_average, long_price_average)

        if self.enter_order_result["long_exchange"].id == "binance":
            real_entry_spread_signed = -real_entry_spread_pct
        else:
            real_entry_spread_signed = real_entry_spread_pct

        print(f"[{self.symbol}] Real Entry spread: {real_entry_spread_signed:.3f}%")
        print(f"[{self.symbol}] [Short] {self.enter_order_result['short_exchange'].id} / {short_price_average}")
        print(f"[{self.symbol}] [Long] {self.enter_order_result['long_exchange'].id} / {long_price_average}")

        self.enter_order_monitor_result["info"] = {"entry_spread": abs(real_entry_spread_pct),
                                                   "entry_spread_signed": real_entry_spread_signed,
                                                   "long_price_average": long_price_average,
                                                   "short_price_average": short_price_average,
                                                   "long_qty": long_qty,
                                                   "short_qty": short_qty,
                                                   "timestamp": time.time()}

    def calculate_average_price(self, long_result, short_result):
        long_cost_list = [x['cost'] for x in long_result if x['price'] is not None]
        short_cost_list = [x['cost'] for x in short_result if x['price'] is not None]

        long_qty, short_qty = self.calculate_sum_qty(long_result, short_result)

        # Division by zero 방지
        if long_qty == 0:
            print(f"⚠️ [{self.symbol}] Long quantity is zero, cannot calculate average price")
            long_price_average = 0
        else:
            long_price_average = sum(long_cost_list) / long_qty

        if short_qty == 0:
            print(f"⚠️ [{self.symbol}] Short quantity is zero, cannot calculate average price")
            short_price_average = 0
        else:
            short_price_average = sum(short_cost_list) / short_qty

        return long_price_average, short_price_average

    @staticmethod
    def calculate_sum_qty(long_result, short_result):
        long_qty_list = [x['qty'] for x in long_result]
        short_qty_list = [x['qty'] for x in short_result]
        return sum(long_qty_list), sum(short_qty_list)

    def append_exit_monitor_result(self, current_data, exit_type: str):
        if exit_type not in ['wrong_entry', 'stop_loss', 'take_profit', 'time_out']:
            print(f"[{self.symbol}] Unknown exit type: {exit_type}")
            return None

        long_price_average, short_price_average = self.calculate_average_price(self.enter_order_monitor_result['long'], self.enter_order_monitor_result['short'])
        for position_direction in ['long', 'short']:
            order_results = self.enter_order_monitor_result[position_direction]
            self.exit_monitor_result[f"{position_direction}_exchange"] = order_results[0]['exchange']
            self.exit_monitor_result[f"{position_direction}_symbol"] = order_results[0]['symbol']
            self.exit_monitor_result[f"{position_direction}_qty"] = sum([order['qty'] for order in order_results])
            self.exit_monitor_result[f"{position_direction}_price"] = long_price_average if position_direction == 'long' else short_price_average

        self.exit_monitor_result |= {
            "exit_spread": abs(current_data['spread_pct']),
            "exit_spread_signed": current_data['spread_pct'],
            "exit_type": exit_type,
            "timestamp": time.time()
        }
        return None
