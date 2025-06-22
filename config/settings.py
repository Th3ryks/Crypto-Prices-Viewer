import os
from dotenv import load_dotenv

def get_token():
    load_dotenv()
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise ValueError("No TELEGRAM_TOKEN found in .env file")
    return token

def get_db_name():
    load_dotenv()
    db_name = os.getenv('DATABASE_NAME')
    if not db_name:
        raise ValueError("DATABASE_NAME not found in .env file")
    return db_name