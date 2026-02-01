import os
import sys

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
# src -> execution_layer -> project_root
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load env
from dotenv import load_dotenv

load_dotenv()

# Import config
try:
    from execution_layer.src.config import Config

    print("Successfully imported Config")

    print(f"BINANCE_API_KEY present: {bool(Config.BINANCE_API_KEY)}")
    print(f"BINANCE_API_SECRET present: {bool(Config.BINANCE_API_SECRET)}")

    if Config.BINANCE_API_KEY and Config.BINANCE_API_KEY == os.getenv("EXCHANGE_KEY"):
        print("SUCCESS: BINANCE_API_KEY matches EXCHANGE_KEY from .env")
    else:
        print(
            f"FAILURE: Key mismatch or missing. Config: {Config.BINANCE_API_KEY[:4]}... .env: {os.getenv('EXCHANGE_KEY')[:4]}..."
        )

except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
