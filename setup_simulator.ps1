<#
.SYNOPSIS
  Simulator one-command setup for any Windows machine.

  Installs Git (via winget when present, direct official installer when not),
  clones or updates the Simulator from GitHub, and pre-creates the virtual
  environment using the bundled Python runtime and offline wheels — no
  internet required after the clone. Full logs go to setup_simulator.log;
  the console shows one line per step with live status.

.USAGE
  irm https://raw.githubusercontent.com/bhadkamkar9snehil/Simulator/main/setup_simulator.ps1 | iex
#>
param(
    [string]$Repo       = "https://github.com/bhadkamkar9snehil/Simulator.git",
    [string]$Branch     = "main",
    [string]$InstallDir = "$HOME\Simulator"
)
$ErrorActionPreference = "Stop"
$Log = Join-Path ([System.IO.Path]::GetTempPath()) "setup_simulator.log"
"Simulator setup $(Get-Date -Format s)" | Out-File $Log

$Sep = "  " + ([string][char]0x2500) * 53   # horizontal rule

function Section($title) {
    Write-Host ""
    Write-Host "  $title" -ForegroundColor DarkGray
}

function Step($name, [scriptblock]$body) {
    Write-Host "    $([char]0x00B7)  $name" -NoNewline
    try {
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $global:LASTEXITCODE = 0
        & $body *>> $Log
        $ErrorActionPreference = $oldEAP
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code $LASTEXITCODE"
        }
        Write-Host "`r    " -NoNewline
        Write-Host ([char]0x2713) -ForegroundColor Green -NoNewline
        Write-Host "  $name"
    } catch {
        Write-Host "`r    " -NoNewline
        Write-Host ([char]0x2717) -ForegroundColor Red -NoNewline
        Write-Host "  $name"
        Write-Host "       $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "       Log: $Log" -ForegroundColor DarkGray
        throw
    }
}

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Ensure-Git {
    if (Get-Command git -ErrorAction SilentlyContinue) { return }
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git -e --silent `
            --accept-source-agreements --accept-package-agreements
    } else {
        $url = "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe"
        $exe = Join-Path $env:TEMP "git-installer.exe"
        Invoke-WebRequest $url -OutFile $exe -ErrorAction Stop
        Start-Process $exe -ArgumentList "/VERYSILENT /NORESTART" -Wait
    }
    Refresh-Path
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git installed but not on PATH - open a new terminal and re-run."
    }
}

# --- Header -------------------------------------------------------------------
Write-Host ""
Write-Host "  Simulator  $([char]0x00B7)  Industrial Data Simulator" -ForegroundColor Cyan
Write-Host $Sep -ForegroundColor DarkGray

# --- Prerequisites ------------------------------------------------------------
Section "Prerequisites"
Step "Git" { Ensure-Git }

# --- Install ------------------------------------------------------------------
Section "Install"
Step "Clone / update" {
    if (Test-Path "$InstallDir\.git") {
        git -C $InstallDir fetch origin $Branch
        git -C $InstallDir checkout $Branch
        git -C $InstallDir reset --hard origin/$Branch
    } else {
        git clone --branch $Branch --single-branch $Repo $InstallDir
    }
}
Set-Location $InstallDir

# --- Prepare environment ------------------------------------------------------
$BundledPy = Join-Path $InstallDir "runtime\python\python.exe"
Section "Prepare"
Step "Bundled runtime" {
    if (-not (Test-Path $BundledPy)) {
        throw "Bundled Python runtime not found at $BundledPy — check that the clone completed."
    }
    & $BundledPy --version
}
Step "Virtual environment" {
    & $BundledPy suite_runtime.py ensure-env
}

# --- Summary ------------------------------------------------------------------
Write-Host ""
Write-Host $Sep -ForegroundColor DarkGray
Write-Host "  " -NoNewline
Write-Host ([char]0x2713) -ForegroundColor Green -NoNewline
Write-Host "  $InstallDir"
Write-Host "  " -NoNewline
Write-Host ([char]0x25B8) -ForegroundColor DarkGray -NoNewline
Write-Host "  Bundled Python  $([char]0x00B7)  offline wheels  $([char]0x00B7)  no internet required" -ForegroundColor DarkGray
Write-Host $Sep -ForegroundColor DarkGray

# --- Next steps ---------------------------------------------------------------
Write-Host ""
Write-Host "  Next steps" -ForegroundColor White
Write-Host ""
Write-Host "  1  Start the simulator" -ForegroundColor DarkGray
Write-Host "       " -NoNewline; Write-Host "double-click  RUN_SIMULATOR.bat" -ForegroundColor Cyan
Write-Host "       or from a terminal:" -ForegroundColor DarkGray
Write-Host "       " -NoNewline; Write-Host "$InstallDir\RUN_SIMULATOR.bat" -ForegroundColor Cyan
Write-Host "       Open " -NoNewline
Write-Host "http://localhost:8001" -ForegroundColor Cyan -NoNewline
Write-Host "  $([char]0x2192)  Portal  $([char]0x2192)  manage simulator" -ForegroundColor DarkGray
Write-Host ""
Write-Host "     Stop: use the portal UI  $([char]0x00B7)  logs: launcher.log" -ForegroundColor DarkGray
Write-Host $Sep -ForegroundColor DarkGray
Write-Host ""
