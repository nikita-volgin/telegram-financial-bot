$root = (Split-Path -Parent $MyInvocation.MyCommand.Path).ToLowerInvariant()
$processes = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($root) -and $_.CommandLine -match 'bot\.py' }
foreach ($process in $processes) { Stop-Process -Id $process.ProcessId -Force }
Write-Host "Stopped $($processes.Count) bot process(es)."
