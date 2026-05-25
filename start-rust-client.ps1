$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Test-PortAvailable([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $iar.AsyncWaitHandle.WaitOne(200, $false)
        if ($connected) {
            $client.EndConnect($iar)
            return $false
        }
        return $true
    } catch {
        return $true
    } finally {
        $client.Close()
    }
}

$preferred = [int]($env:MODELING_WORKBENCH_PORT)
if (-not $preferred) {
    $preferred = 8765
}

$port = $preferred
while (-not (Test-PortAvailable $port)) {
    $port++
    if ($port -gt ($preferred + 50)) {
        throw "没有找到可用端口"
    }
}

$env:MODELING_WORKBENCH_PORT = "$port"
$env:MODELING_WORKBENCH_APP_ROOT = $root
$env:MODELING_WORKBENCH_DATA_ROOT = Join-Path $root "data"

cargo build --manifest-path .\rust-backend\Cargo.toml | Out-Host

$exe = Join-Path $root "rust-backend\target\debug\modeling-workbench-server.exe"
$server = Start-Process -FilePath $exe -WorkingDirectory $root -WindowStyle Hidden -PassThru
$url = "http://127.0.0.1:$port"

try {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            Invoke-RestMethod "$url/api/health" | Out-Null
            break
        } catch {
            Start-Sleep -Milliseconds 400
        }
    } while ((Get-Date) -lt $deadline)

    Start-Process $url
    Write-Host "Rust 客户端已打开：$url"
    Write-Host "按 Enter 停止 Rust 后端。"
    [Console]::ReadLine() | Out-Null
} finally {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
