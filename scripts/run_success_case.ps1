$ErrorActionPreference = "Stop"

$transactionId = "T-demo-success-" + (Get-Date -Format "yyyyMMddHHmmssfff")

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
    -Body $body

Write-Host "Transaction ID: $transactionId"
Invoke-RestMethod http://127.0.0.1:8000/metrics/messages
