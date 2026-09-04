import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lunchsync.db")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SWIGGY_CLIENT_ID = os.getenv("SWIGGY_CLIENT_ID") or "swiggy-mcp"
SWIGGY_CLIENT_SECRET = os.getenv("SWIGGY_CLIENT_SECRET", "")
SWIGGY_BASE_URL = os.getenv("SWIGGY_BASE_URL") or "https://mcp.swiggy.com"


