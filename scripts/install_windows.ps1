param(
    [switch]$Repair,
    [switch]$Update,
    [switch]$SkipSelfTest,
    [ValidateRange(1, 65535)]
    [int]$Port = 7865
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

. (Join-Path $PSScriptRoot 'ui_windows.ps1')

function Download-File([string]$Uri, [string]$Destination) {
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -fL --retry 3 --connect-timeout 20 -o $Destination $Uri
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $Uri" }
        return
    }
    Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination
}

function Install-UvStandalone([string]$DestinationDir, [string]$ExpectedExe) {
    $rawArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    $arch = if ($rawArch) { $rawArch.ToUpperInvariant() } else { 'UNKNOWN' }

    switch ($arch) {
        'AMD64' { $target = 'x86_64-pc-windows-msvc' }
        'ARM64' { $target = 'aarch64-pc-windows-msvc' }
        default { throw "Unsupported Windows architecture for uv bootstrap: $arch" }
    }

    $assetName = "uv-$target.zip"
    $downloadUrl = "https://github.com/astral-sh/uv/releases/latest/download/$assetName"
    $tempZip = Join-Path ([System.IO.Path]::GetTempPath()) "morphorum-uv-$PID.zip"

    try {
        Step "Downloading standalone uv for $arch..."
        Download-File $downloadUrl $tempZip
        if (-not (Test-Path $tempZip)) { throw 'uv archive download did not produce a file.' }
        if ((Get-Item $tempZip).Length -lt 1024) { throw 'uv archive download appears invalid or incomplete.' }

        if (Test-Path $DestinationDir) {
            Get-ChildItem -Force $DestinationDir -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
        }

        try { Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop }
        catch { Add-Type -AssemblyName System.IO.Compression -ErrorAction Stop }
        [System.IO.Compression.ZipFile]::ExtractToDirectory($tempZip, $DestinationDir)
    }
    finally {
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path $ExpectedExe)) {
        $found = Get-ChildItem -Path $DestinationDir -Filter 'uv.exe' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { Copy-Item $found.FullName $ExpectedExe -Force }
    }
    if (-not (Test-Path $ExpectedExe)) {
        throw "Standalone uv archive extracted, but uv.exe was not found under $DestinationDir."
    }
}

$RuntimeDir = Join-Path $Root '.runtime'
$UvDir = Join-Path $RuntimeDir 'uv'
$UvExe = Join-Path $UvDir 'uv.exe'
$PythonDir = Join-Path $RuntimeDir 'python'
$UvCache = Join-Path $RuntimeDir 'uv-cache'
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'

$env:UV_INSTALL_DIR = $UvDir
$env:UV_NO_MODIFY_PATH = '1'
$env:UV_PYTHON_INSTALL_DIR = $PythonDir
$env:UV_CACHE_DIR = $UvCache
$env:UV_PROJECT_ENVIRONMENT = (Join-Path $Root '.venv')
$env:HF_HOME = Join-Path $Root 'cache\huggingface'
$env:HF_HUB_DISABLE_TELEMETRY = '1'

$dirs = @(
    $RuntimeDir, $UvDir, $PythonDir, $UvCache,
    (Join-Path $Root 'data'), (Join-Path $Root 'projects'),
    (Join-Path $Root 'outputs'), (Join-Path $Root 'logs'),
    (Join-Path $Root 'cache'), (Join-Path $Root 'cache\huggingface'),
    (Join-Path $Root 'backups')
)
foreach ($dir in $dirs) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

$mode = if ($Repair) { 'repair' } elseif ($Update) { 'update' } else { 'install' }
$logPath = Join-Path $Root "logs\$mode.log"
Start-Transcript -Path $logPath -Append | Out-Null

try {
    Show-MorphorumBanner -Mode $mode
    Write-MorphorumSection 'SYSTEM CHECKS'
    Write-MorphorumDetail 'Mode' $mode
    Write-MorphorumDetail 'Location' $Root

    Write-MorphorumSection 'SERVER PREFERENCES'
    $PortFile = Join-Path $Root 'data\server-port.txt'
    $ServerPort = 7865
    $ExistingPort = $false
    if (Test-Path $PortFile) {
        $rawPort = (Get-Content -LiteralPath $PortFile -Raw).Trim()
        $parsedPort = 0
        if ([int]::TryParse($rawPort, [ref]$parsedPort) -and
            $parsedPort -ge 1 -and $parsedPort -le 65535) {
            $ServerPort = $parsedPort
            $ExistingPort = $true
        } else {
            Warn 'The saved server port is invalid. Using 7865 until corrected.'
        }
    }
    $SavePort = $false
    if (-not $Repair -and -not $Update) {
        if ($PSBoundParameters.ContainsKey('Port')) {
            $ServerPort = $Port
            $SavePort = $true
        } elseif (-not $ExistingPort) {
            Write-Host '  Choose the port Morphorum should listen on.' -ForegroundColor Gray
            Write-Host '  Press ENTER for 7865 (recommended).' -ForegroundColor DarkGray
            while ($true) {
                $choice = (Read-Host '  Server port').Trim()
                if (-not $choice) { break }
                $requested = 0
                if ([int]::TryParse($choice, [ref]$requested) -and
                    $requested -ge 1 -and $requested -le 65535) {
                    $ServerPort = $requested
                    break
                }
                Warn 'Enter a valid port between 1 and 65535, or press Enter for 7865.'
            }
            $SavePort = $true
        }
    }
    Write-MorphorumDetail 'Server port' ([string]$ServerPort)
    if ($ExistingPort -and -not $SavePort) { Okay 'Existing server port setting preserved.' }

    try {
        $driveRoot = [System.IO.Path]::GetPathRoot($Root)
        $drive = [System.IO.DriveInfo]::new($driveRoot)
        $freeGiB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
        if ($freeGiB -lt 8) { throw "Only $freeGiB GiB free on $driveRoot. The initial image-generation runtime needs at least 8 GiB free." }
        Okay "Disk space: $freeGiB GiB free"
    } catch {
        if ($_.Exception.Message -like 'Only *') { throw }
        Warn "Could not determine free disk space: $($_.Exception.Message)"
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Step 'Git not found; installing Git with winget...'
            winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw 'Git installation failed.' }
        } else { throw 'Git is required and neither Git nor winget is available.' }
    } else { Okay "$(git --version)" }

    Write-MorphorumSection 'PYTHON RUNTIME'
    if (-not (Test-Path $UvExe)) {
        Step 'Installing Morphorum-owned uv runtime manager...'
        Install-UvStandalone $UvDir $UvExe
    }
    Okay "uv: $(& $UvExe --version)"

    Step 'Ensuring managed Python 3.12 runtime...'
    & $UvExe python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'uv could not install/find Python 3.12.' }

    if (-not (Test-Path $VenvPython)) {
        Step 'Creating Morphorum virtual environment...'
        & $UvExe venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) { throw 'uv failed to create .venv.' }
    }

    $torchVersion = '2.14.0'
    $nvidiaExpected = $false
    $gpu = $null
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $gpu = nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null
        $nvidiaExpected = $true
        if ($gpu) { Okay "NVIDIA GPU: $($gpu -join '; ')" } else { Okay 'NVIDIA driver tools detected.' }
    } else {
        Warn 'nvidia-smi not detected; PyTorch backend auto-detection will fall back to CPU if no supported GPU is available.'
    }

    # Let uv select the most compatible PyTorch backend for the installed hardware.
    # This also applies while resolving Morphorum dependencies such as accelerate.
    $env:UV_TORCH_BACKEND = 'auto'
    Write-MorphorumSection 'AI DEPENDENCIES'
    Step 'Installing/updating Morphorum Python dependencies...'
    & $UvExe pip install --python $VenvPython --upgrade --editable .
    if ($LASTEXITCODE -ne 0) { throw 'Morphorum dependency installation failed.' }

    # Install Torch LAST. Some ordinary PyPI dependency resolutions can otherwise
    # replace a CUDA wheel with a newer CPU-only torch build.
    Step "Installing PyTorch $torchVersion with automatic hardware backend selection..."
    & $UvExe pip install --python $VenvPython --upgrade --reinstall-package torch "torch==$torchVersion" --torch-backend=auto
    if ($LASTEXITCODE -ne 0) { throw "PyTorch $torchVersion hardware-specific installation failed." }

    Okay "Python: $(& $VenvPython --version)"

    $torchInfo = & $VenvPython -c "import torch; print(f'PyTorch {torch.__version__}; CUDA build {torch.version.cuda}; CUDA available {torch.cuda.is_available()}')"
    if ($LASTEXITCODE -ne 0) { throw 'PyTorch installed but could not be imported.' }
    Okay $torchInfo

    if ($nvidiaExpected) {
        $cudaCheck = & $VenvPython -c "import torch,sys; ok=torch.cuda.is_available() and torch.version.cuda is not None; print('1' if ok else '0'); sys.exit(0 if ok else 2)"
        if ($LASTEXITCODE -ne 0 -or ($cudaCheck | Select-Object -Last 1).Trim() -ne '1') {
            throw 'NVIDIA GPU detected, but Morphorum ended with a CPU-only or unusable PyTorch build. The installer will not silently continue with CPU generation.'
        }

        $cudaSmoke = & $VenvPython -c "import torch; x=torch.ones((64,64), device='cuda'); torch.cuda.synchronize(); print(f'{torch.cuda.get_device_name(0)}; CUDA {torch.version.cuda}; tensor OK')"
        if ($LASTEXITCODE -ne 0) {
            throw 'CUDA-enabled PyTorch installed, but a simple GPU tensor test failed.'
        }
        Okay "CUDA smoke test: $cudaSmoke"
    }

    Write-MorphorumSection 'USER SETTINGS + MEDIA TOOLS'
    if (-not $Repair -and -not $Update) {
        # Capture genuinely fresh provenance BEFORE copying config or seeding Default.
        & $VenvPython -m morphorum setup-state prepare
        if ($LASTEXITCODE -ne 0) { throw 'Could not prepare first-run setup state.' }
    }
    $userConfig = Join-Path $Root 'data\config.yaml'
    if (-not (Test-Path $userConfig)) {
        Copy-Item (Join-Path $Root 'config\default.yaml') $userConfig
        Okay 'Created user configuration: data\config.yaml'
    } else { Okay 'Existing user configuration preserved.' }

    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Step 'FFmpeg not found; installing Gyan.FFmpeg with winget...'
            winget install --id Gyan.FFmpeg -e --source winget --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { Warn 'FFmpeg installation failed. Video encoding will not work until FFmpeg is installed.' }
            else { Okay 'FFmpeg installed. A new terminal may be required before its command alias appears.' }
        } else { Warn 'FFmpeg not found and winget is unavailable. Video encoding will require FFmpeg.' }
    } else { Okay 'FFmpeg found.' }

    # Seed from the bundled Default.json only for brand-new installs.
    # Repairs and updates must never create or overwrite user projects.
    if (-not $Repair -and -not $Update) {
        Write-MorphorumSection 'STARTER PROJECT'
        Step 'Checking whether a starter project is needed...'
        & $VenvPython -m morphorum seed-example
        if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the Default starter project.' }
    } else {
        Okay 'Existing animation projects preserved.'
    }

    Write-MorphorumSection 'INSTALLATION VERIFICATION'
    if (-not $SkipSelfTest) {
        Step 'Running Morphorum self-test...'
        & $VenvPython -m morphorum self-test
        if ($LASTEXITCODE -ne 0) { throw 'Morphorum self-test failed.' }
        Okay 'Morphorum self-test passed.'
    }

    if ($SavePort) {
        Set-Content -LiteralPath $PortFile -Value ([string]$ServerPort) -Encoding ASCII
        Okay 'Server port preference saved for future launches.'
    }

    if (-not $Repair -and -not $Update) {
        # Mark ready after checks AND saved port successfully completed.
        & $VenvPython -m morphorum setup-state ready
        if ($LASTEXITCODE -ne 0) { throw 'Could not finalize first-run setup state.' }
    }

    Write-MorphorumSection 'MORPHORUM IS READY'
    Okay 'Installation successful.'
    Write-MorphorumDetail 'Server port' ([string]$ServerPort)
    Write-MorphorumNext 'Local launch' "$Root\run.bat"
    Write-MorphorumNext 'LAN launch' "$Root\run-lan.bat"
    Write-MorphorumNext 'Update' "$Root\update.bat"
    Write-MorphorumNext 'Diagnostics' "$Root\repair.bat"
    Write-MorphorumDetail 'Install log' $logPath
    Write-Host ''
}
catch {
    Write-Host ''
    Fail $_.Exception.Message
    Write-Host "Installer log: $logPath"
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
}
