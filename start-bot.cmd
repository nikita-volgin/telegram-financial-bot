@echo off
cd /d "%~dp0"
start "Expense Keeper Bot" /b ".venv\Scripts\python.exe" bot.py >> "bot.log" 2>&1
echo Bot started. If it doesn't reply, open bot.log.
