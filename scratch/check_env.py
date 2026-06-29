import os
from pathlib import Path
from dotenv import load_dotenv

# Root is one level up from scratch
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

default_from = os.getenv('DEFAULT_FROM_EMAIL')
print(f"DEFAULT_FROM_EMAIL value: |{default_from}|")
