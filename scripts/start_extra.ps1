# 启动一个额外的前端实例(独立窗口, 关窗即停)
#
# 用法(项目根目录):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_extra.ps1 -Port 8503
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_extra.ps1 -Port 8504 -App frontend/admin.py
param(
    [int]$Port = 8503,
    [string]$App = "frontend/app.py"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$psExe = (Get-Process -Id $PID).Path

$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$busy = $false
try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $Port); $c.Close(); $busy = $true } catch {}
if ($busy) {
    Write-Host "[跳过] $Port 已在运行" -ForegroundColor DarkGray
    exit 0
}

Write-Host "[启动] $App -> http://127.0.0.1:$Port" -ForegroundColor Green
Start-Process $psExe -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root'; `$env:PYTHONIOENCODING='utf-8'; python -m streamlit run $App --server.address 127.0.0.1 --server.port $Port --server.headless true --browser.gatherUsageStats false"
) -WindowStyle Hidden

Start-Sleep -Seconds 12
try {
    $r = Invoke-WebRequest "http://127.0.0.1:$Port/_stcore/health" -UseBasicParsing -TimeoutSec 8
    Write-Host "  $Port : HTTP $($r.StatusCode) OK -> http://127.0.0.1:$Port" -ForegroundColor Green
} catch {
    Write-Host "  $Port : 未就绪(可能仍在启动, 稍等几秒再刷新)" -ForegroundColor Yellow
}
