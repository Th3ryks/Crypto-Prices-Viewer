import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DATABASE_NAME")
DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            chat_id INTEGER,
            ticker TEXT,
            PRIMARY KEY (chat_id, ticker)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def add_ticker(chat_id: int, ticker: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO tickers (chat_id, ticker) VALUES (?, ?)", (chat_id, ticker.upper()))
    conn.commit()
    conn.close()

def remove_ticker(chat_id: int, ticker: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tickers WHERE chat_id = ? AND ticker = ?", (chat_id, ticker.upper()))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected

def get_tickers(chat_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT ticker FROM tickers WHERE chat_id = ?", (chat_id,))
    tickers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tickers