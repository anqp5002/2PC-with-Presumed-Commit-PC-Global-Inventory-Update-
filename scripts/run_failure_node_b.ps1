$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $PSScriptRoot
$transactionId = "T-demo-site-b-crash-ready-" + (Get-Date -Format "yyyyMMddHHmmssfff")

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

function Restart-SiteB {
    $pythonExe = Resolve-Python
    $pythonCall = "& '$pythonExe'"
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$root'; `$Host.UI.RawUI.WindowTitle = '2PC Participant site_b :8002 recovery'; `$env:SITE_ID='site_b'; `$env:REGION='Central'; `$env:PORT='8002'; $pythonCall -m uvicorn participant.app:app --host 127.0.0.1 --port 8002"
    )
}

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8002/debug/reset" `
    -ErrorAction SilentlyContinue

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8002/debug/crash-after-ready?enabled=true"

$body = @{
    transaction_id = $transactionId
    mode = "PC_WITH_ACD"
    updates = @(
        @{
            inventory_id = "INV-000001"
            warehouse_id = "WH001"
            region = "North"
            delta_quantity = -1
        },
        @{
            inventory_id = "INV-001251"
            warehouse_id = "WH006"
            region = "Central"
            delta_quantity = -1
        },
        @{
            inventory_id = "INV-002501"
            warehouse_id = "WH011"
            region = "SouthEast"
            delta_quantity = -1
        },
        @{
            inventory_id = "INV-003751"
            warehouse_id = "WH016"
            region = "Mekong"
            delta_quantity = -1
        }
    )
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/transactions/global-inventory-update" `
    -ContentType "application/json" `
    -Body $body `
    -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2
Restart-SiteB
Start-Sleep -Seconds 5

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8002/recover-pending" `
    -ErrorAction SilentlyContinue

Write-Host "Transaction ID: $transactionId"
Invoke-RestMethod "http://127.0.0.1:8000/transactions/$transactionId"
Invoke-RestMethod "http://127.0.0.1:8002/logs/$transactionId"
