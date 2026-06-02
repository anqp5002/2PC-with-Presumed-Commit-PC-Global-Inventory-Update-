$ErrorActionPreference = "Stop"
$transactionId = "T-demo-timeout-" + (Get-Date -Format "yyyyMMddHHmmssfff")

try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:8002/debug/prepare-delay?seconds=5"

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
            }
        )
    } | ConvertTo-Json -Depth 6

    Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:8000/transactions/global-inventory-update" `
        -ContentType "application/json" `
        -Body $body

    Write-Host "Transaction ID: $transactionId"
    Invoke-RestMethod "http://127.0.0.1:8000/transactions/$transactionId"
}
finally {
    Start-Sleep -Seconds 6
    Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:8002/debug/reset" `
        -ErrorAction SilentlyContinue
}
