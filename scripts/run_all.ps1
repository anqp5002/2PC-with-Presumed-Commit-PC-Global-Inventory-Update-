$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

function Resolve-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }

    throw "Python was not found. Activate a virtual environment or install Python first."
}

$pythonExe = Resolve-Python
$pythonCall = "& '$pythonExe'"

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$Command
    )

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$root'; `$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    )
}

Start-ServiceWindow `
    -Title "2PC Coordinator :8000" `
    -Command "$pythonCall -m uvicorn coordinator.app:app --host 127.0.0.1 --port 8000"

Start-ServiceWindow `
    -Title "2PC Participant site_a :8001" `
    -Command "`$env:SITE_ID='site_a'; `$env:REGION='North'; `$env:PORT='8001'; $pythonCall -m uvicorn participant.app:app --host 127.0.0.1 --port 8001"

Start-ServiceWindow `
    -Title "2PC Participant site_b :8002" `
    -Command "`$env:SITE_ID='site_b'; `$env:REGION='Central'; `$env:PORT='8002'; $pythonCall -m uvicorn participant.app:app --host 127.0.0.1 --port 8002"

Start-ServiceWindow `
    -Title "2PC Participant site_c :8003" `
    -Command "`$env:SITE_ID='site_c'; `$env:REGION='SouthEast'; `$env:PORT='8003'; $pythonCall -m uvicorn participant.app:app --host 127.0.0.1 --port 8003"

Start-ServiceWindow `
    -Title "2PC Participant site_d :8004" `
    -Command "`$env:SITE_ID='site_d'; `$env:REGION='Mekong'; `$env:PORT='8004'; $pythonCall -m uvicorn participant.app:app --host 127.0.0.1 --port 8004"

Write-Host "Started coordinator and participants."
Write-Host "Coordinator: http://127.0.0.1:8000"
Write-Host "site_a:      http://127.0.0.1:8001"
Write-Host "site_b:      http://127.0.0.1:8002"
Write-Host "site_c:      http://127.0.0.1:8003"
Write-Host "site_d:      http://127.0.0.1:8004"
