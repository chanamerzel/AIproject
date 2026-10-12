# One-time Gmail login for the decision emails sent by the worker through the Gmail MCP server.
# Runs `gmail-mcp auth` in the worker image with port 3000 published, so Google's redirect to
# http://localhost:3000/oauth2callback reaches the container. The login token is written to
# secrets\gmail\credentials.json (mounted as /root/.gmail-mcp). Never commit that folder.
# Prerequisites: secrets\gmail\gcp-oauth.keys.json (Google OAuth client, Desktop app) and an image
# built from the current Dockerfile (`docker compose build`).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\gmail_auth.ps1 [-NoBrowser]
param([switch]$NoBrowser)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$folder = Join-Path $root "secrets\gmail"
$keys = Join-Path $folder "gcp-oauth.keys.json"
$token = Join-Path $folder "credentials.json"
$name = "fitscreen-gmail-auth"

New-Item -ItemType Directory -Force -Path $folder | Out-Null
if (-not (Test-Path $keys)) {
    Write-Host "Missing $keys"
    Write-Host "Download the OAuth client JSON from Google Cloud (Credentials > OAuth client, type Desktop app) and save it under that name."
    exit 1
}
try {
    $json = Get-Content $keys -Raw | ConvertFrom-Json
} catch {
    Write-Host "$keys is not valid JSON."
    exit 1
}
if (-not ($json.installed -or $json.web)) {
    Write-Host "$keys has neither an 'installed' nor a 'web' section. Download the OAuth client JSON again."
    exit 1
}

try {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, 3000)
    $probe.Start()
    $probe.Stop()
} catch {
    Write-Host "Port 3000 is in use on this computer. Free it and run again (Google redirects to localhost:3000)."
    exit 1
}

docker rm -f $name 2>$null | Out-Null
# --no-deps: do not start or recreate the web container.
$null = docker compose run -d --no-deps --name $name -p 3000:3000 worker gmail-mcp auth
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not start the auth container. Is Docker running, and was the image built with 'docker compose build'?"
    exit 1
}

try {
    $url = $null
    for ($i = 0; $i -lt 60 -and -not $url; $i++) {
        Start-Sleep -Milliseconds 500
        $logs = (docker logs $name 2>&1) -join "`n"
        if ($logs -match "(https://accounts\.google\.com/\S+)") { $url = $Matches[1] }
        if ((docker inspect -f "{{.State.Running}}" $name) -ne "true") { break }
    }
    if (-not $url) {
        Write-Host "gmail-mcp did not print a login URL. Container output:"
        docker logs $name 2>&1 | ForEach-Object { "$_" }
        exit 1
    }
    Write-Host "Sign in with the Gmail account that should send the emails:"
    Write-Host $url
    if (-not $NoBrowser) { Start-Process $url }
    Write-Host "Waiting for Google to redirect back to localhost:3000 (Ctrl+C to cancel)..."
    $code = docker wait $name
    if ($code -eq "0" -and (Test-Path $token)) {
        Write-Host "Gmail connected. Token saved to $token"
        Write-Host "The worker picks it up on its next poll; no restart needed."
        exit 0
    }
    docker logs --tail 15 $name 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -notmatch "accounts\.google\.com" }
    Write-Host "Gmail login failed (exit code $code). Common causes: the account is not a test user on the"
    Write-Host "OAuth consent screen, the Gmail API is not enabled, or the OAuth client JSON was replaced."
    exit 1
} finally {
    docker rm -f $name 2>$null | Out-Null
}
