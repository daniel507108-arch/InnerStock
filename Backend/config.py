from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")