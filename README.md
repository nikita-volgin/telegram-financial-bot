# Expense Keeper Telegram bot

Personal expense tracker built from the supplied specification. It uses SQLite and keeps every user's data isolated by Telegram user ID.

## Install and run (Windows)

1. Python 3.12 is included locally in `.python`; no system-wide installation is required.
2. In PowerShell, open this directory and run (the environment has already been created):

   ```powershell
   .\.venv\Scripts\python.exe bot.py
   ```

3. Put the token received from `@BotFather` and your numeric Telegram ID in `.env`. You can learn the ID from `@userinfobot`.

The bot long-polls Telegram. It is currently running in the background; when launched from PowerShell, keep the window open while using it.

If PowerShell blocks `.ps1` files, start it by double-clicking `start-bot.cmd` instead.

## Commands

`/start`, `/help`, `/categories`, `/day [DD.MM or YYYY-MM-DD]`, `/report [today|week|month|DD.MM-DD.MM]`, `/settings`.

Expenses are accepted as `Хлеб 200`, `200 хлеб`, `Такси 1500 #Транспорт`, and with a date suffix: `Хлеб 200 вчера` or `Хлеб 200 03.08`.
