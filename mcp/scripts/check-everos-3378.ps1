param(
    [string]$BaseUrl = "http://127.0.0.1:3378"
)

$ErrorActionPreference = "Stop"

$healthUrl = "$BaseUrl/health"
$response = Invoke-RestMethod -Method Get -Uri $healthUrl -TimeoutSec 10
$response | ConvertTo-Json -Depth 8
