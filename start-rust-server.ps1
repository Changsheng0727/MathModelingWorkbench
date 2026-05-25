$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$env:MODELING_WORKBENCH_APP_ROOT = $root
$env:MODELING_WORKBENCH_DATA_ROOT = Join-Path $root "data"

cargo run --manifest-path .\rust-backend\Cargo.toml
