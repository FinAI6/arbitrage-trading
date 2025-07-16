import asyncio
from collections import deque
from typing import Optional, Tuple, Dict, Any
from config_manager import ConfigManager
import ccxt.pro as ccxt


class ApiManager:
    def __init__(self):
        self.config_manager = ConfigManager()

        # API 키 정보 가져오기
        self.binance_api_key = self.config_manager.get('EXCHANGE', 'binance_api_key')
        self.binance_api_secret = self.config_manager.get('EXCHANGE', 'binance_api_secret')

        self.bybit_api_key = self.config_manager.get('EXCHANGE', 'bybit_api_key')
        self.bybit_api_secret = self.config_manager.get('EXCHANGE', 'bybit_api_secret')

        self.max_trading_num = self.config_manager.getint('TRADING', 'max_symbols')

        # Thread-safe deque
        self.api_deque = deque()
        self._api_deque_lock = asyncio.Lock()

        # Load Market Update deque
        self.update_only_api = None
        self.shared_markets: list = [None, None]

        # Set Leverage, Margin Mode List
        self.leverage_margin_done_list: list = []

        # API 설정 정보
        self.binance_config = {
            'apiKey': self.binance_api_key,
            'secret': self.binance_api_secret,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True
            },
            'enableRateLimit': False,
        }

        self.bybit_config = {
            'apiKey': self.bybit_api_key,
            'secret': self.bybit_api_secret,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True
            },
            'enableRateLimit': False,
        }

        self._initialized = False
        self._load_markets_task = None
        self._load_markets_interval = 3  # 1시간마다 load_markets 실행
        self._running = False

        # 백그라운드에서 초기화 시작
        self._init_task = asyncio.create_task(self._background_initialize())

    def _create_api_pair(self) -> Tuple[ccxt.Exchange, ccxt.Exchange]:
        """새로운 API 쌍 생성"""
        binance_api = ccxt.binance(self.binance_config)
        bybit_api = ccxt.bybit(self.bybit_config)

        binance_api.options['maxRetriesOnFailure'] = 43200
        binance_api.options['maxRetriesOnFailureDelay'] = 1000

        bybit_api.options['maxRetriesOnFailure'] = 43200
        bybit_api.options['maxRetriesOnFailureDelay'] = 1000

        return binance_api, bybit_api

    async def _load_markets_for_pair(self, api_pair: Tuple[ccxt.Exchange, ccxt.Exchange]):
        """API 쌍에 대해 load_markets 실행"""
        binance_api, bybit_api = api_pair
        try:
            # 동시에 load_markets 실행
            await asyncio.gather(
                binance_api.load_markets(),
                bybit_api.load_markets()
            )
            # print(f"✅ Markets loaded for API pair")
        except Exception as e:
            print(f"❌ Failed to load markets for API pair: {e}")

    async def _background_initialize(self):
        """백그라운드에서 초기화 실행"""
        if self._initialized:
            return

        print(f"🔄 Background initializing {self.max_trading_num} API pairs...")

        try:
            # API 쌍들 생성 및 load_markets 실행
            for i in range(self.max_trading_num):
                api_pair = self._create_api_pair()
                await self._load_markets_for_pair(api_pair)

                # 락으로 보호하여 deque에 추가
                async with self._api_deque_lock:
                    self.api_deque.append(api_pair)

                print(f"✅ API pair {i + 1}/{self.max_trading_num} initialized")

            # Update Only Deque 생성
            self.update_only_api = self._create_api_pair()
            await self._load_markets_for_pair(self.update_only_api)

            # shared_markets 초기화 추가
            for i in range(2):
                self.shared_markets[i] = self.update_only_api[i].markets.copy()

            self._initialized = True
            self._running = True

        except Exception as e:
            print(f"❌ Background initialization failed: {e}")

    async def start(self):
        # 초기화 완료 대기
        await self.wait_for_initialization()

        # 주기적 load_markets 작업 시작
        self._load_markets_task = asyncio.create_task(self._periodic_load_markets())
        print(f"🔄 Started periodic load_markets task (interval: {self._load_markets_interval}s)")

    async def _periodic_load_markets(self):
        """주기적으로 API 쌍 하나씩 load_markets 실행"""
        while self._running:
            try:
                # print(f"🔄 Starting periodic load_markets...")

                await self._load_markets_for_pair(self.update_only_api)
                for i in range(2):
                    self.shared_markets[i] = self.update_only_api[i].markets.copy()

                # # Todo: Update 주기를 어떻게 할건지? 한번에 다? 일정 간격으로?
                # for _ in range(len(self.update_only_api_deque)):
                #     # 락으로 보호하여 하나만 가져오기
                #     api_pair = None
                #     async with self._api_deque_lock:
                #         if self.api_deque:
                #             api_pair = self.api_deque.pop()
                #
                #     if api_pair:
                #         # 락 해제 후 load_markets 실행 (시간이 오래 걸리는 작업)
                #         await self._load_markets_for_pair(api_pair)
                #
                #         # 락으로 보호하여 앞쪽에 다시 추가 (최신 것을 앞쪽에)
                #         async with self._api_deque_lock:
                #             self.api_deque.appendleft(api_pair)
                #
                #         print(f"✅ Refreshed API pair markets")

                await asyncio.sleep(self._load_markets_interval)

            except Exception as e:
                print(f"❌ Error during periodic load_markets: {e}")
                await asyncio.sleep(60)  # 에러 발생 시 1분 대기

    async def wait_for_initialization(self, timeout: float = 60.0):
        """초기화 완료까지 대기"""
        if self._initialized:
            return True

        try:
            await asyncio.wait_for(self._init_task, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            print(f"❌ Initialization timeout after {timeout} seconds")
            return False

    async def get_api_pair(self, timeout: float = 10.0) -> Optional[Tuple[ccxt.Exchange, ccxt.Exchange]]:
        """API 쌍 가져오기 (가장 최신 것을 우선적으로)"""
        # 초기화가 완료될 때까지 대기
        # if not self._initialized:
        #     print("⏳ Waiting for API manager initialization...")
        #     await self.wait_for_initialization()

        if not self._initialized:
            raise Exception("API Manager initialization failed")

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            # 락으로 보호하여 가져오기
            async with self._api_deque_lock:
                if self.api_deque:
                    # 가장 최신 것을 가져옴 (앞쪽에서)
                    api_pair = self.api_deque.popleft()
                    # Markets 최신 정보 업데이트
                    for i in range(2):
                        api_pair[i].set_markets(self.shared_markets[i])
                    return api_pair

            # 잠깐 대기 후 다시 시도
            await asyncio.sleep(0.1)

        raise Exception(f"Timeout: No available API pair within {timeout} seconds")

    async def return_api_pair(self, api_pair: Tuple[ccxt.Exchange, ccxt.Exchange]):
        """API 쌍 반환 (앞쪽에 추가하여 재사용 우선순위 높임)"""
        # 락으로 보호하여 반환
        async with self._api_deque_lock:
            self.api_deque.append(api_pair)

    async def get_queue_status(self) -> Dict[str, Any]:
        """큐 상태 확인"""
        async with self._api_deque_lock:
            deque_size = len(self.api_deque)

        return {
            'deque_size': deque_size,
            'max_api_pairs': self.max_trading_num,
            'initialized': self._initialized,
            'periodic_load_markets_running': self._running,
            'load_markets_interval': self._load_markets_interval
        }

    def set_load_markets_interval(self, interval: int):
        """load_markets 실행 간격 설정 (초 단위)"""
        self._load_markets_interval = interval
        print(f"🔄 Load markets interval set to {interval} seconds")

    async def force_load_markets(self):
        """모든 API 쌍에 대해 즉시 load_markets 실행"""
        if not self._initialized:
            print("❌ API Manager not initialized")
            return

        print("🔄 Force loading markets ...")

        await self._load_markets_for_pair(self.update_only_api)
        for i in range(2):
            self.shared_markets[i] = self.update_only_api[i].markets.copy()

        # # 락으로 보호하여 모든 API 쌍 가져오기
        # temp_pairs = []
        # async with self._api_deque_lock:
        #     while self.api_deque:
        #         api_pair = self.api_deque.popleft()
        #         temp_pairs.append(api_pair)
        #
        # # 락 해제 후 각 API 쌍에 대해 load_markets 실행
        # refreshed_pairs = []
        # for api_pair in temp_pairs:
        #     await self._load_markets_for_pair(api_pair)
        #     refreshed_pairs.append(api_pair)
        #
        # # 락으로 보호하여 다시 deque에 추가
        # async with self._api_deque_lock:
        #     self.api_deque.extend(refreshed_pairs)

        print(f"✅ Force load_markets completed")

    def add_leverage_margin_done_list(self, symbol: str):
        self.leverage_margin_done_list.append(symbol)

    def check_leverage_margin_done_list(self, symbol: str) -> bool:
        if symbol in self.leverage_margin_done_list:
            return True
        else:
            return False

    async def stop(self):
        """모든 API 인스턴스 종료 및 정리"""
        print("🔄 Closing all API instances...")

        # 주기적 load_markets 작업 중지
        self._running = False
        if self._load_markets_task:
            self._load_markets_task.cancel()
            try:
                await self._load_markets_task
            except asyncio.CancelledError:
                pass

        # 초기화 작업 중지
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
            try:
                await self._init_task
            except asyncio.CancelledError:
                pass

        # 락으로 보호하여 deque의 API들 종료
        async with self._api_deque_lock:
            while self.api_deque:
                try:
                    binance_api, bybit_api = self.api_deque.popleft()
                    await binance_api.close()
                    await bybit_api.close()
                except Exception as e:
                    print(f"❌ Error closing API pair: {e}")

        print("✅ All API instances closed")


# 사용 예제
async def example_usage():
    """사용 예제"""
    # 객체 생성 시 백그라운드에서 초기화 시작
    api_manager = ApiManager()

    # load_markets 간격을 30분으로 설정
    api_manager.set_load_markets_interval(1800)  # 30분

    try:
        # API 쌍 가져오기 (초기화가 완료될 때까지 자동 대기)
        binance_api, bybit_api = await api_manager.get_api_pair()

        print(f"✅ Got API pair - Binance: {binance_api.id}, Bybit: {bybit_api.id}")

        # API 사용 예제
        binance_balance = await binance_api.fetch_balance()
        bybit_balance = await bybit_api.fetch_balance()

        print(f"Binance USDT Balance: {binance_balance.get('USDT', {}).get('free', 0)}")
        print(f"Bybit USDT Balance: {bybit_balance.get('USDT', {}).get('free', 0)}")

        # API 쌍 반환
        await api_manager.return_api_pair((binance_api, bybit_api))

        # 큐 상태 확인
        status = await api_manager.get_queue_status()
        print(f"Queue status: {status}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # 모든 API 종료
        await api_manager.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())