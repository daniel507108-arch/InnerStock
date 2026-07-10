from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT")

from config import ANTHROPIC_API_KEY
print("Key loaded:", ANTHROPIC_API_KEY is not None)