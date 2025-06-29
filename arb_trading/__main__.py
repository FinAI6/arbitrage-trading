# arb_trading/__main__.py (경로 및 import 수정)
import asyncio
import argparse
import sys
import signal
from pathlib import Path
from arb_trading.config.settings import ConfigManager
from arb_trading.core.arbitrage_engine import ArbitrageEngine
from arb_trading.utils.logger import setup_logger
from arb_trading.utils.platform_utils import setup_windows_event_loop


def parse_arguments():
    """명령행 인수 파싱"""
    parser = argparse.ArgumentParser(
        description='암호화폐 차익거래 자동화 시스템',
        epilog="""
사용 예시:
  python -m arb_trading --simulation                    # 시뮬레이션 모드
  python -m arb_trading --performance --log-level DEBUG # 디버그 + 성능 모니터링
  python -m arb_trading --config custom.json           # 커스텀 설정 파일
  python -m arb_trading --spread-threshold 0.3         # 스프레드 임계값 0.3%
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        metavar='FILE',
        help='설정 파일 경로 (기본: config/default_config.json)'
    )

    parser.add_argument(
        '--simulation', '-s',
        action='store_true',
        help='시뮬레이션 모드로 실행 (실제 거래 안함)'
    )

    parser.add_argument(
        '--performance', '-p',
        action='store_true',
        help='성능 모니터링 활성화 (상세 로깅)'
    )

    parser.add_argument(
        '--log-level', '-l',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='로그 레벨 설정 (기본: INFO)'
    )

    parser.add_argument(
        '--log-file',
        type=str,
        default='logs/arbitrage.log',
        metavar='FILE',
        help='로그 파일 경로 (기본: logs/arbitrage.log)'
    )

    parser.add_argument(
        '--order-type',
        type=str,
        default='limit',
        choices=['limit', 'market'],
        help='기본 주문 타입 (기본: limit)'
    )

    parser.add_argument(
        '--max-positions',
        type=int,
        default=None,
        metavar='N',
        help='최대 포지션 수 (기본: 3)'
    )

    parser.add_argument(
        '--spread-threshold',
        type=float,
        default=None,
        metavar='PCT',
        help='스프레드 임계값 %% (기본: 0.5)'
    )

    parser.add_argument(
        '--fetch-interval',
        type=int,
        default=None,
        metavar='SEC',
        help='데이터 조회 간격 초 (기본: 5)'
    )

    parser.add_argument(
        '--create-config',
        type=str,
        metavar='FILE',
        help='설정 파일 템플릿 생성 후 종료'
    )

    parser.add_argument(
        '--version', '-v',
        action='version',
        version='차익거래 시스템 v1.0.0'
    )

    return parser.parse_args()


async def main():
    """메인 함수"""
    # Windows 환경 설정
    setup_windows_event_loop()

    args = parse_arguments()

    # 설정 파일 생성 요청 처리
    if args.create_config:
        from . import create_config_template
        create_config_template(args.create_config)
        return

    # 로거 설정
    logger = setup_logger(
        name="main",
        log_file=args.log_file,
        level=args.log_level
    )

    engine = None

    try:
        logger.info("=" * 60)
        logger.info("🚀 차익거래 시스템 시작")
        logger.info(f"📁 작업 디렉토리: {Path.cwd()}")
        logger.info(f"🐍 Python 버전: {sys.version.split()[0]}")
        logger.info(f"💻 플랫폼: {sys.platform}")
        logger.info("=" * 60)

        # 설정 로드
        try:
            config_manager = ConfigManager(args.config)
            logger.info(f"✅ 설정 파일 로드 완료: {config_manager.config_path}")
        except Exception as e:
            logger.error(f"❌ 설정 파일 로드 실패: {e}")
            logger.info("💡 설정 파일 생성: python -m arb_trading --create-config config.json")
            return

        # 명령행 인수로 설정 덮어쓰기
        config_updates = []

        if args.simulation:
            config_manager.update_config('trading', 'simulation_mode', True)
            config_updates.append("시뮬레이션 모드")

        if args.performance:
            config_manager.update_config('monitoring', 'performance_logging', True)
            config_updates.append("성능 모니터링")

        if args.order_type:
            config_manager.update_config('orders', 'default_type', args.order_type)
            config_updates.append(f"주문 타입: {args.order_type}")

        if args.max_positions:
            config_manager.update_config('trading', 'max_positions', args.max_positions)
            config_updates.append(f"최대 포지션: {args.max_positions}")

        if args.spread_threshold:
            config_manager.update_config('trading', 'spread_threshold', args.spread_threshold)
            config_updates.append(f"스프레드 임계값: {args.spread_threshold}%")

        if args.fetch_interval:
            config_manager.update_config('monitoring', 'fetch_interval', args.fetch_interval)
            config_updates.append(f"조회 간격: {args.fetch_interval}초")

        if config_updates:
            logger.info(f"⚙️ 설정 업데이트: {', '.join(config_updates)}")

        # 현재 설정 요약 표시
        trading_config = config_manager.trading
        monitoring_config = config_manager.monitoring

        logger.info("📋 현재 설정:")
        logger.info(f"   모드: {'🔍 시뮬레이션' if trading_config.simulation_mode else '💰 실거래'}")
        logger.info(f"   스프레드 임계값: {trading_config.spread_threshold}%")
        logger.info(f"   최대 포지션: {trading_config.max_positions}개")
        logger.info(f"   조회 간격: {monitoring_config.fetch_interval}초")
        logger.info(f"   성능 모니터링: {'✅' if monitoring_config.performance_logging else '❌'}")

        # 거래소 설정 표시
        exchanges_config = config_manager.exchanges
        logger.info("🏪 거래소 설정:")
        for name, config in exchanges_config.items():
            if config.enabled:
                mode = "📊 데이터만" if config.fetch_only else "💸 거래가능"
                api_status = "🔑 API키 설정됨" if config.api_key else "🔓 API키 없음"
                logger.info(f"   {name.upper()}: {mode} ({api_status})")

        # 엔진 생성 및 실행
        engine = ArbitrageEngine(config_manager)
        await engine.run()

    except KeyboardInterrupt:
        logger.info("⏹️ 사용자에 의한 종료 요청")
    except Exception as e:
        logger.error(f"💥 예상치 못한 오류: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)
    finally:
        if engine:
            await engine.cleanup()
        logger.info("🏁 프로그램 종료")


def run():
    """동기 실행 래퍼"""
    # Windows 환경 설정
    setup_windows_event_loop()

    # 기본 시그널 핸들러 설정
    def signal_handler(signum, frame):
        print(f"\n⏹️ 종료 신호 수신: {signum}")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🏁 프로그램이 종료되었습니다.")
    except Exception as e:
        print(f"💥 실행 중 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()

