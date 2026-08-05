$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList 'bot.py' -WorkingDirectory $root -WindowStyle Hidden
Write-Host 'Expense bot started.'
