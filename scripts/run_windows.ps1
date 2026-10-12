param(
    [switch]$Lan,
    [Alias("backend-only")]
    [switch]$BackendOnly,
    [ValidateRange(1, 65535)]
    [int]$Port = 7865
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'ui_windows.ps1')
Set-Location $Root
$Python = Join-Path $Root '.venv\Scripts\python.exe'
# A command-line -Port applies to this launch only. Otherwise use the
# installer's saved preference, falling back to Morphorum's default.
$PortSource = if ($PSBoundParameters.ContainsKey('Port')) { 'command line' } elseif ($BackendOnly) { 'backend default' } else { 'default' }
if ($BackendOnly -and -not $PSBoundParameters.ContainsKey('Port')) { $Port = 7866 }
if (-not $BackendOnly -and -not $PSBoundParameters.ContainsKey('Port')) {
    $portFile = Join-Path $Root 'data\server-port.txt'
    if (Test-Path $portFile) {
        $rawPort = (Get-Content -LiteralPath $portFile -Raw).Trim()
        $savedPort = 0
        if ([int]::TryParse($rawPort, [ref]$savedPort) -and
            $savedPort -ge 1 -and $savedPort -le 65535) {
            $Port = $savedPort
            $PortSource = 'installed setting'
        } else {
            Write-Host '  [!] Saved server port is invalid. Falling back to 7865.' -ForegroundColor Yellow
        }
    }
}

$env:HF_HUB_DISABLE_PROGRESS_BARS = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'

Show-MorphorumBanner -Mode $(if ($BackendOnly) { if ($Lan) { 'API ONLY / LAN' } else { 'API ONLY / LOCAL' } } elseif ($Lan) { 'RUN / LAN' } else { 'RUN / LOCAL' })
Write-MorphorumSection 'STARTUP CHECKS'
Write-MorphorumDetail 'Location' $Root
Write-MorphorumDetail 'Server port' "$Port ($PortSource)"
if ($BackendOnly) { Write-MorphorumDetail 'Server mode' 'Backend API only (token protected)' }

if (-not (Test-Path $Python)) {
    Fail 'Morphorum runtime is not installed. Run install.bat first.'
    exit 1
}
try {
    $version = & $Python --version
    if ($LASTEXITCODE -ne 0) { throw 'Python runtime could not start.' }
    Okay "Python: $version"
} catch {
    Fail $_.Exception.Message
    exit 1
}

$hostAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$branch = ''
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        $branch = (& git -C $Root rev-parse --abbrev-ref HEAD 2>$null | Select-Object -First 1)
        if ($branch) { $branch = $branch.Trim() }
    } catch { $branch = '' }
}
if ($branch) { Write-MorphorumDetail 'Git branch' $branch }

Write-MorphorumSection 'ACCESS'
Write-MorphorumNext 'This computer' "http://127.0.0.1:$Port"
if ($Lan) {
    Warn 'LAN access enabled: Morphorum listens on all network interfaces.'
    if ($BackendOnly) {
        Warn 'Backend API requires a bearer token. Use trusted private networks or VPN; do not expose to the internet.'
    } else {
        Warn 'Only run on a trusted private network. This service is not password-protected.'
    }
    try {
        $addresses = @(
            Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
              Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
              Select-Object -ExpandProperty IPAddress -Unique
        )
        foreach ($address in $addresses) {
            Write-MorphorumNext 'From your LAN' "http://$($address):$Port"
        }
        if (-not $addresses.Count) {
            Warn 'No LAN address detected. Use this computer IPv4 address to connect from another device.'
        }
    } catch {
        Warn 'Could not discover LAN IP automatically. Find your IPv4 address with ipconfig.'
    }
} else {
    Okay 'Local-only mode: the server is not available to other devices.'
}

Write-MorphorumSection 'SERVER'
if ($BackendOnly) {
    Write-MorphorumDetail 'API token file' (Join-Path $Root 'data\backend-access-token')
    Step 'Starting Morphorum API-only mode. Use a native client with a bearer token.'
} else {
    Step 'Starting Morphorum. Leave this window open while using the app.'
}
Write-Host '  Press Ctrl+C to stop the server.' -ForegroundColor DarkGray
Write-Host ''
$serveArgs = @('-m', 'morphorum', 'serve', '--host', $hostAddress, '--port', [string]$Port)
if ($BackendOnly) { $serveArgs += '--backend-only' }
& $Python @serveArgs
$code = $LASTEXITCODE
if ($code -ne 0) { Fail "Server stopped with exit code $code." }
else { Okay 'Morphorum server stopped.' }
exit $code
