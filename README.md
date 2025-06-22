# 💸 Crypto Price Tracking Telegram Bot

A Telegram bot built with **Aiogram** that tracks real-time cryptocurrency prices using **Binance API**, provides charts 📊, performs conversions 🔄, and manages tracked coins per user/group.

---

## 🚀 Features

- 🟢 `/start` - Start tracking default coins (BTC, ETH, SOL)
- ❌ `/stop` - Stop tracking prices
- ➕ `/add <ticker>` - Add a coin to track (e.g., `/add BTC`)
- ➖ `/remove <ticker>` - Remove a coin from tracking
- 📈 `/chart <ticker> <time>` - Show historical chart (e.g., `/chart BTC 7d`)
- 💱 `/convert <value> <from> to <to>` - Convert between coins (e.g., `/convert 0.1 BTC to USDC`)
- 📋 `/help` - Show available commands

> ⚠️ Only coins listed on **Binance** are supported.  
> 📌 Supports automatic pinning of the latest price message.

---

## 🧰 Tech Stack

- 🐍 Python 3.10+
- 📦 Aiogram 3.x
- 🧠 SQLite (via `sqlite3`)
- 📡 Binance REST & WebSocket API
- 🖼 Matplotlib (for charting)
- 🌐 `.env` configuration via `python-dotenv`

---

## 📦 Installation

```bash
git clone https://github.com/Th3ryks/Crypto-Prices-Viewer.git
cd Crypto-Prices-Viewer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Create a `.env` file in the root directory:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_NAME=crypto.db
```

---

## ▶️ Run the Bot

```bash
python main.py
```

The bot will:

- Start polling Telegram updates
- Connect to Binance WebSocket
- Initialize database
- Respond to users and update prices every 10 seconds

---

## 📂 Project Structure

```
bot/
├── crypto_api.py      # Binance API integration
├── database.py        # SQLite DB interactions
├── handlers.py        # Telegram message & command handlers
├── utils.py           # Message helpers and retry logic
config/
└── settings.py        # Token and config loading
main.py                # Entry point
.env                   # Environment variables
requirements.txt       # Python dependencies
```

---

## 🛡 Admin Controls

- Only group **admins** can add or remove tracked coins
- Bot can pin/unpin price messages in groups
- Old prices auto-update every 10 seconds

---

## 📌 Example Commands

```plaintext
/add BTC
/remove ETH
/chart SOL 7d
/convert 0.5 BTC to USDC
```

---

## 🧪 Testing

You can test locally using a test Telegram bot token and chat ID. Charts are rendered with `matplotlib` and sent as images.

---

## 📜 License

MIT License. Feel free to use and modify. Contributions welcome!

---

## 👨‍💻 Author

Created with ❤️ by Th3ryks