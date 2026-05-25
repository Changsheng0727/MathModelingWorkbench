$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$appName = "MathModelingWorkbench"
$displayName = "Math Modeling Workbench"
$releaseDir = Join-Path $root "release"
$installerWorkDir = Join-Path $releaseDir "installer"
$distAppDir = Join-Path $root "dist\$appName"
$zipPath = Join-Path $releaseDir "$appName-Windows-x64.zip"
$setupPath = Join-Path $releaseDir "$appName-Setup.exe"
$sedPath = Join-Path $releaseDir "$appName-Setup.sed"
$pandocReferenceSource = "E:\AI_MATHMODELING\dongSanShengB\B题\pandoc模板.docx"
$pandocReferenceDest = Join-Path $root "app\resources\pandoc_reference.docx"
$frontendDir = Join-Path $root "frontend"

Write-Host "==> Installing desktop build dependencies"
python -m pip install -r (Join-Path $root "requirements-desktop.txt")

if (Test-Path (Join-Path $frontendDir "package.json")) {
  Write-Host "==> Building Next.js frontend"
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if (-not $npm) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
  }
  if (-not $npm) {
    throw "Node.js/npm is required to build the Next.js frontend. Install Node.js 22+ and retry."
  }
  $npmPath = if ($npm.Path) { $npm.Path } else { $npm.Source }
  Push-Location $frontendDir
  try {
    if (Test-Path (Join-Path $frontendDir "package-lock.json")) {
      & $npmPath ci
    } else {
      & $npmPath install
    }
    if ($LASTEXITCODE -ne 0) {
      throw "npm dependency installation failed with exit code $LASTEXITCODE"
    }
    & $npmPath run build
    if ($LASTEXITCODE -ne 0) {
      throw "Next.js frontend build failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

Write-Host "==> Bundling Pandoc Word reference template"
New-Item -ItemType Directory -Force (Split-Path -Parent $pandocReferenceDest) | Out-Null
if (Test-Path $pandocReferenceSource) {
  Copy-Item -LiteralPath $pandocReferenceSource -Destination $pandocReferenceDest -Force
} elseif (-not (Test-Path $pandocReferenceDest)) {
  throw "Pandoc reference template is missing: $pandocReferenceSource"
} else {
  Write-Warning "Pandoc reference source was not found; using existing bundled copy: $pandocReferenceDest"
}

Write-Host "==> Cleaning previous build output"
Remove-Item -Recurse -Force (Join-Path $root "build") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $root "dist") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $releaseDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $releaseDir | Out-Null

Write-Host "==> Building desktop executable with PyInstaller"
python -m PyInstaller `
  --noconfirm `
  --clean `
  --name $appName `
  --windowed `
  --hidden-import app.main `
  --hidden-import uvicorn `
  --hidden-import uvicorn.lifespan.on `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --collect-submodules app `
  --collect-all webview `
  --collect-all pandas `
  --collect-all numpy `
  --collect-all matplotlib `
  --collect-all sklearn `
  --collect-all scipy `
  --collect-all openpyxl `
  --collect-all docx `
  --exclude-module PyQt5 `
  --exclude-module PyQt6 `
  --exclude-module PySide2 `
  --exclude-module PySide6 `
  --exclude-module IPython `
  --exclude-module pytest `
  --add-data "app;app" `
  ".\client\desktop_client.py"

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force (Join-Path $distAppDir "data\projects") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $distAppDir "data\settings\templates") | Out-Null
Copy-Item (Join-Path $root "WINDOWS_CLIENT.md") (Join-Path $distAppDir "WINDOWS_CLIENT.md") -Force -ErrorAction SilentlyContinue

Write-Host "==> Creating portable zip package"
for ($zipAttempt = 1; $zipAttempt -le 5; $zipAttempt++) {
  try {
    Compress-Archive -Path (Join-Path $distAppDir "*") -DestinationPath $zipPath -Force
    break
  } catch {
    if ($zipAttempt -eq 5) {
      throw
    }
    Write-Warning "Portable zip creation failed on attempt $zipAttempt; retrying after file handles settle. $($_.Exception.Message)"
    Start-Sleep -Seconds 3
  }
}

Write-Host "==> Preparing installer payload"
New-Item -ItemType Directory -Force $installerWorkDir | Out-Null
Copy-Item $zipPath (Join-Path $installerWorkDir (Split-Path -Leaf $zipPath)) -Force

$installScript = @'
$ErrorActionPreference = "Stop"

$appName = "MathModelingWorkbench"
$displayName = "Math Modeling Workbench"
$installDir = Join-Path $env:LOCALAPPDATA $appName
$dataBackup = Join-Path $env:TEMP "$appName-data-backup"
$zipPath = Join-Path $PSScriptRoot "$appName-Windows-x64.zip"

if (-not (Test-Path $zipPath)) {
    throw "Installer payload is missing: $zipPath"
}

Remove-Item -Recurse -Force $dataBackup -ErrorAction SilentlyContinue
if (Test-Path (Join-Path $installDir "data")) {
    Move-Item -Path (Join-Path $installDir "data") -Destination $dataBackup -Force
}
if (Test-Path $installDir) {
    Remove-Item -Recurse -Force $installDir
}
New-Item -ItemType Directory -Force $installDir | Out-Null
Expand-Archive -Path $zipPath -DestinationPath $installDir -Force
if (Test-Path $dataBackup) {
    Remove-Item -Recurse -Force (Join-Path $installDir "data") -ErrorAction SilentlyContinue
    Move-Item -Path $dataBackup -Destination (Join-Path $installDir "data") -Force
}

$exePath = Join-Path $installDir "$appName.exe"
if (-not (Test-Path $exePath)) {
    throw "Application executable was not found: $exePath"
}

$uninstallPath = Join-Path $installDir "uninstall.ps1"
@"
`$ErrorActionPreference = "Stop"
`$appName = "$appName"
`$displayName = "$displayName"
`$installDir = Join-Path `$env:LOCALAPPDATA `$appName
`$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "`$displayName.lnk"
`$startMenuDir = Join-Path `$env:APPDATA "Microsoft\Windows\Start Menu\Programs\`$displayName"
Remove-Item -Force `$desktopShortcut -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force `$startMenuDir -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force `$installDir -ErrorAction SilentlyContinue
"@ | Set-Content -Path $uninstallPath -Encoding UTF8

$wsh = New-Object -ComObject WScript.Shell
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$displayName.lnk"
$shortcut = $wsh.CreateShortcut($desktopShortcut)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $installDir
$shortcut.Description = $displayName
$shortcut.Save()

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$displayName"
New-Item -ItemType Directory -Force $startMenuDir | Out-Null
$startShortcut = Join-Path $startMenuDir "$displayName.lnk"
$shortcut = $wsh.CreateShortcut($startShortcut)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $installDir
$shortcut.Description = $displayName
$shortcut.Save()

$uninstallShortcut = Join-Path $startMenuDir "Uninstall $displayName.lnk"
$shortcut = $wsh.CreateShortcut($uninstallShortcut)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$uninstallPath`""
$shortcut.WorkingDirectory = $installDir
$shortcut.Description = "Uninstall $displayName"
$shortcut.Save()

Start-Process -FilePath $exePath -WorkingDirectory $installDir
'@

$installScript | Set-Content -Path (Join-Path $installerWorkDir "install.ps1") -Encoding UTF8

$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=$displayName has been installed.
TargetName=$setupPath
FriendlyName=$displayName Setup
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1
PostInstallCmd=<None>
AdminQuietInstCmd=powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1
UserQuietInstCmd=powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=$installerWorkDir

[SourceFiles0]
install.ps1=
$(Split-Path -Leaf $zipPath)=
"@

$sed | Set-Content -Path $sedPath -Encoding ASCII

Write-Host "==> Creating Windows setup exe with IExpress"
& "$env:WINDIR\System32\iexpress.exe" /N /Q $sedPath

if (-not (Test-Path $setupPath)) {
    Write-Warning "IExpress did not generate a setup exe. Trying 7-Zip SFX fallback."
    $sevenZip = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if (-not $sevenZip) {
        throw "Setup exe was not generated and 7z.exe was not found. Portable zip is available: $zipPath"
    }

    $sfxCandidates = @()
    $sfxCandidates += "C:\Scoop\apps\7zip\current\7z.sfx"
    $sfxCandidates += "C:\Scoop\apps\7zip\24.09\7z.sfx"
    $sfxCandidates += "C:\Program Files\7-Zip\7z.sfx"
    $sfxPath = $sfxCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $sfxPath) {
        $sfxPath = Get-ChildItem -Path "C:\Scoop\apps\7zip","C:\Program Files\7-Zip" -Recurse -Filter "7z.sfx" -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $sfxPath) {
        throw "Setup exe was not generated and 7z.sfx was not found. Portable zip is available: $zipPath"
    }

    $payloadArchive = Join-Path $releaseDir "$appName-SetupPayload.7z"
    $sfxConfig = Join-Path $releaseDir "$appName-SfxConfig.txt"
    Remove-Item -Force $payloadArchive, $sfxConfig, $setupPath -ErrorAction SilentlyContinue

    Push-Location $installerWorkDir
    try {
        & $sevenZip.Source a -t7z $payloadArchive ".\*" -mx=7 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "7z archive creation failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }

@"
;!@Install@!UTF-8!
Title="$displayName Setup"
BeginPrompt="Install $displayName?"
RunProgram="powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1"
;!@InstallEnd@!
"@ | Set-Content -Path $sfxConfig -Encoding UTF8

    $outStream = [System.IO.File]::Open($setupPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
    try {
        foreach ($part in @($sfxPath, $sfxConfig, $payloadArchive)) {
            $bytes = [System.IO.File]::ReadAllBytes($part)
            $outStream.Write($bytes, 0, $bytes.Length)
        }
    } finally {
        $outStream.Close()
    }
    if (-not (Test-Path $setupPath)) {
        throw "7-Zip SFX setup exe was not generated: $setupPath"
    }
}

Write-Host ""
Write-Host "Build completed."
Write-Host "Portable exe: $distAppDir\$appName.exe"
Write-Host "Portable zip: $zipPath"
Write-Host "Installer exe: $setupPath"
