$ErrorActionPreference = "SilentlyContinue"

$ports = @(8000, 8001, 8002, 8003, 8004)

foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen
    foreach ($connection in $connections) {
        $processId = $connection.OwningProcess
        if ($processId) {
            Write-Host "Stopping process $processId on port $port"
            Stop-Process -Id $processId -Force
        }
    }
}

Write-Host "Stop request completed."

