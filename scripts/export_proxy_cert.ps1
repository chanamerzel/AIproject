# Exports HTTPS-filter root certificates (e.g. Symen / NetFree) from the Windows store into certs/
# so the Docker image trusts them. Without this, containers fail TLS to Tavily, Gemini and model downloads.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\export_proxy_cert.ps1 [-Match "Symen|NetFree"]
param([string]$Match = "Symen|NetFree")

$target = Join-Path $PSScriptRoot "..\certs"
New-Item -ItemType Directory -Force -Path $target | Out-Null

$now = Get-Date
$certs = Get-ChildItem Cert:\LocalMachine\Root, Cert:\CurrentUser\Root |
    Where-Object { $_.Subject -match $Match -and $_.NotAfter -gt $now } |
    Sort-Object Thumbprint -Unique

if (-not $certs) {
    Write-Host "No valid root certificate matching '$Match' found. Nothing to export."
    exit 0
}

foreach ($c in $certs) {
    $b64 = [Convert]::ToBase64String($c.RawData, "InsertLineBreaks")
    $path = Join-Path $target ("proxy-" + $c.Thumbprint.Substring(0, 8) + ".crt")
    "-----BEGIN CERTIFICATE-----`n$b64`n-----END CERTIFICATE-----`n" | Set-Content -Path $path -Encoding ascii -NoNewline
    Write-Host "exported $($c.Subject) -> $path"
}
