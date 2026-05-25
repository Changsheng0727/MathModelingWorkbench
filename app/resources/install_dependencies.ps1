param(
    [string]$LogPath = "",
    [switch]$Force
)

$ErrorActionPreference = "Continue"

if (-not $LogPath) {
    $LogPath = Join-Path $env:TEMP "MathModelingWorkbench-dependency-install.log"
}

$logDir = Split-Path -Parent $LogPath
New-Item -ItemType Directory -Force $logDir | Out-Null
$statusPath = Join-Path $logDir "dependency_status.json"
$lockPath = Join-Path $logDir "dependency_install.lock"

function Write-DepLog([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

function Save-Status([hashtable]$Status) {
    $Status.generated_at = (Get-Date).ToString("s")
    $Status | ConvertTo-Json -Depth 8 | Set-Content -Path $statusPath -Encoding UTF8
}

$lockStream = $null
try {
    if ((Test-Path $lockPath) -and -not $Force) {
        Write-DepLog "Another dependency installer appears to be running; exiting."
        return
    }
    $lockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch {
    Write-DepLog "Could not create lock file: $($_.Exception.Message)"
    return
}

try {
    Write-DepLog "Dependency check started."
    $machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$machinePath;$userPath;$env:PATH"

    $dependencies = @(
        @{
            name = "Pandoc"
            command = "pandoc"
            winget_id = "JohnMacFarlane.Pandoc"
            purpose = "Word export and legacy DOC parsing"
        },
        @{
            name = "MiKTeX / XeLaTeX"
            command = "xelatex"
            winget_id = "MiKTeX.MiKTeX"
            purpose = "LaTeX PDF compilation"
        }
    )

    function Test-Dependency([hashtable]$Dep) {
        $cmd = Get-Command $Dep.command -ErrorAction SilentlyContinue
        if (-not $cmd) {
            return @{
                name = $Dep.name
                command = $Dep.command
                winget_id = $Dep.winget_id
                available = $false
                executable = ""
                detail = "not found"
            }
        }
        return @{
            name = $Dep.name
            command = $Dep.command
            winget_id = $Dep.winget_id
            available = $true
            executable = $cmd.Source
            detail = "found"
        }
    }

    function Find-Winget {
        $cmd = Get-Command winget -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
        $candidate = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"
        if (Test-Path $candidate) {
            return $candidate
        }
        $windowsApps = Join-Path $env:ProgramFiles "WindowsApps"
        $found = Get-ChildItem -Path $windowsApps -Filter winget.exe -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        return $found
    }

    $before = @()
    foreach ($dep in $dependencies) {
        $before += Test-Dependency $dep
    }
    $missing = @($before | Where-Object { -not $_.available })
    $winget = Find-Winget

    $status = @{
        status = "checking"
        winget = @{
            available = [bool]$winget
            executable = "$winget"
        }
        dependencies = $before
        attempted = @()
        log = $LogPath
    }
    Save-Status $status

    if (-not $missing.Count) {
        Write-DepLog "All external dependencies are available."
        $status.status = "ready"
        Save-Status $status
        return
    }

    if (-not $winget) {
        Write-DepLog "winget is not available; cannot automatically download missing dependencies."
        $status.status = "manual_required"
        $status.message = "winget was not found. Install Windows App Installer or manually install missing dependencies."
        Save-Status $status
        return
    }

    $status.status = "installing"
    Save-Status $status

    foreach ($item in $missing) {
        Write-DepLog "Installing $($item.name) with winget package $($item.winget_id)."
        $args = @(
            "install",
            "--id", $item.winget_id,
            "--exact",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements"
        )
        $proc = Start-Process -FilePath $winget -ArgumentList $args -Wait -PassThru -WindowStyle Hidden
        $attempt = @{
            name = $item.name
            winget_id = $item.winget_id
            exit_code = $proc.ExitCode
        }
        if ($proc.ExitCode -ne 0) {
            Write-DepLog "Silent install failed for $($item.name) with exit code $($proc.ExitCode); retrying without --silent."
            $args = @(
                "install",
                "--id", $item.winget_id,
                "--exact",
                "--accept-package-agreements",
                "--accept-source-agreements"
            )
            $proc = Start-Process -FilePath $winget -ArgumentList $args -Wait -PassThru
            $attempt.retry_exit_code = $proc.ExitCode
        }
        $status.attempted += $attempt
        Save-Status $status
    }

    $machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$machinePath;$userPath;$env:PATH"
    $after = @()
    foreach ($dep in $dependencies) {
        $after += Test-Dependency $dep
    }
    $stillMissing = @($after | Where-Object { -not $_.available })
    $status.dependencies = $after
    if ($stillMissing.Count) {
        $status.status = "partial"
        $status.message = "Some dependencies are still missing after installation. Restart the app or install them manually."
        Write-DepLog "Dependency install finished with missing dependencies remaining."
    } else {
        $status.status = "ready"
        $status.message = "External dependencies are installed or already available."
        Write-DepLog "Dependency install finished successfully."
    }
    Save-Status $status
} finally {
    if ($lockStream) {
        $lockStream.Close()
    }
    Remove-Item -Force $lockPath -ErrorAction SilentlyContinue
}
