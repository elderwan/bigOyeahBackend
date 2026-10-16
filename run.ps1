Set-Location $PSScriptRoot
& .\.venv\Scripts\Activate.ps1
Write-Host "Starting backend server on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
