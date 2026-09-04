import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lunchsync.db")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SWIGGY_CLIENT_ID = os.getenv("SWIGGY_CLIENT_ID") or "swiggy-mcp"
SWIGGY_CLIENT_SECRET = os.getenv("SWIGGY_CLIENT_SECRET", "")
SWIGGY_BASE_URL = os.getenv("SWIGGY_BASE_URL") or "https://mcp.swiggy.com"


