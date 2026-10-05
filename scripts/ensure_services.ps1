# -*- coding: utf-8 -*-
# 服务的「操作系统级」兜底: 交给 Windows 任务计划程序每分钟跑一次。
#
# 为什么要这一层: 之前服务与看门狗都是我从会话里 Start-Process 拉起来的, 它们
# 依附于会话的进程树, 会话一清理就整批消失(用户看到的就是「页面加载失败
# ERR_CONNECTION_REFUSED」)。交给任务计划程序启动后, 进程归 svchost 所有,
# 不再随会话消失。
#
# 本脚本只做一件事, 且必须快速返回(每分钟都会被调用一次):
#   把掉线的服务补齐(调 start_all.ps1, 它是幂等的: 活着的跳过)
# 用锁文件避免上一轮还没跑完就被下一轮叠加。
# 注: 看门狗(watch_services.ps1)已按用户要求移除, 本脚本不再拉起它。

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "logs\ensure.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $log -Value $line -Encoding UTF8
    $lines = Get-Content $log -ErrorAction SilentlyContinue
    if ($lines -and $lines.Count -gt 300) {
        $lines | Select-Object -Last 150 | Set-Content -Path $log -Encoding UTF8
    }
}

# ---- 单实例锁: 120 秒内的重复调用直接退出 ----
$lock = Join-Path $root "logs\ensure.lock"
if (Test-Path $lock) {
    $age = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($age.TotalSeconds -lt 120) { exit 0 }
}
Set-Content -Path $lock -Value (Get-Date -Format "s") -Encoding ASCII

function Test-Port($port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $port)
        $c.Close()
        return $true
    } catch { return $false }
}

try {
    # ---- 服务 ----
    $down = @()
    foreach ($p in 8000, 8501, 8502, 8591) { if (-not (Test-Port $p)) { $down += $p } }

    if ($down.Count -gt 0) {
        Write-Log ("掉线: " + ($down -join ", ") + " -> 拉起")
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "start_all.ps1")
        ) -WindowStyle Hidden -PassThru
        if (-not $proc.WaitForExit(240000)) {
            try { $proc.Kill() } catch { }
            Write-Log "start_all.ps1 超时(240s), 已终止"
        }
        Start-Sleep -Seconds 6
        $still = @()
        foreach ($p in $down) { if (-not (Test-Port $p)) { $still += $p } }
        if ($still.Count -gt 0) { Write-Log ("仍未恢复: " + ($still -join ", ")) }
        else { Write-Log ("已恢复: " + ($down -join ", ")) }
    }
} catch {
    Write-Log ("异常: " + $_.Exception.Message)
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
