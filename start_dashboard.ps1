param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host '[1/3] Running dashboard data pipeline...'
python -X utf8 -m src.main run_all --input market-data-auto.xlsx

Write-Host ''
Write-Host '[2/3] Running Agent anomaly insights...'
python -X utf8 -m src.main run_agent_insights --dashboard-data frontend/data/dashboard_data.json --out frontend/data/agent_insights.json

Write-Host ''
Write-Host '[3/3] Starting http.server on http://127.0.0.1:8000 ...'
Start-Process -WindowStyle Hidden -FilePath python -ArgumentList @('-X','utf8','-m','http.server','8000','-d','frontend') -WorkingDirectory $root

Start-Sleep -Seconds 2

$chrome = Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
if (Test-Path $chrome) {
    Start-Process -WindowStyle Hidden -FilePath $chrome -ArgumentList @('--new-window', 'http://127.0.0.1:8000')
} else {
    Start-Process 'http://127.0.0.1:8000'
}

Write-Host ''
Write-Host 'Server started.'
Write-Host 'Open http://127.0.0.1:8000 in your browser.'
