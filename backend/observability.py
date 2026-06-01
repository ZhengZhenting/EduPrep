import os
import uuid
from dotenv import load_dotenv
from loguru import logger
from langfuse import get_client

load_dotenv()

# Loguru setup
logger.remove() 

logger.add(
    sink=lambda msg: print(msg, end=""),
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan> | {message}",
    level="INFO",
    colorize=True
)

# output format
logger.add(
    "logs/eduprep.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
    level="INFO",
    rotation="10 MB",      # not more than 10MB
    retention="7 days",    # remain for 7 days
    serialize=True         # JSON format
)


# initialise LangFuse 
langfuse = get_client()  # read .env automaticly

def generate_request_id() -> str:
    return str(uuid.uuid4())[:8]

def verify_langfuse():
    try:
        langfuse.auth_check()
        logger.info("LangFuse connection verified")
        return True
    except Exception as e:
        logger.warning(f"LangFuse connection failed: {e}")
        return False
