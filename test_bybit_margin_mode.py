from api_manager import ApiManager
import asyncio
import sys

if sys.platform.startswith("win"):
    # Windows: keep the selector loop you already use
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

else:  # Linux / macOS
    try:
        import uvloop  # pip install uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        print("✅  uvloop enabled (Unix)")
    except ImportError:
        print("⚠️  uvloop not installed – falling back to default loop")


async def quick_test():
    api_manager = ApiManager()
    _, bybit = api_manager._create_api_pair()
    print("loading markets...")
    await bybit.load_markets()
    try:
        print("setting margin mode...")
        print(await bybit.set_margin_mode("isolated", "ARC/USDT:USDT"))
    except Exception as e:
        print(f"error: {e}")


if __name__ == "__main__":
    asyncio.run(quick_test())