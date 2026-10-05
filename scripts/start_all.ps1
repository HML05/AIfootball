# 足球数据系统 - 一键启动(后端 API + 用户端 + 管理后台)
#
# 用法(在项目根目录执行):
#     pwsh -File scripts\start_all.ps1          # PowerShell 7
#     powershell -File scripts\start_all.ps1    # Windows PowerShell
#
# 每个服务在独立窗口运行, 关掉窗口即停止; 不依赖任何后台任务跟踪。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONIOENCODING = "utf-8"
$psExe = (Get-Process -Id $PID).Path   # 当前宿主的 PowerShell(pwsh 7 或 Windows PowerShell 5.1)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "项目目录: $root" -ForegroundColor Cyan
Write-Host "检查依赖..." -ForegroundColor Cyan
python -c "import streamlit, pandas, xgboost, fastapi, uvicorn; print('依赖 OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "依赖缺失, 请先执行: pip install streamlit pandas xgboost fastapi uvicorn apscheduler python-dotenv" -ForegroundColor Yellow
    exit 1
}

function Test-Port($port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $port)
        $c.Close()
        return $true
    } catch { return $false }
}

# 0) 清理重复实例(只清「不在监听」的残留进程, 不动正在服务的那个)
# 教训: Windows 允许同时监听 127.0.0.1:8000 与 0.0.0.0:8000, 于是「先起一个、
# 再起一个」会留下两个 uvicorn, 请求随机落到其中一个, 表现为接口时好时坏
# (二维码接口偶发 500 就是这么来的)。这里按命令行特征找出同类进程, 跳过真正
# 在监听的那个, 其余残留一律清掉, 保证每类服务只有一个实例。
function Remove-Duplicates($pattern, $port, $label) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $listeners = @()
    if ($conns) { $listeners = @($conns.OwningProcess | Sort-Object -Unique) }
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$pattern*" }
    foreach ($p in $procs) {
        if ($listeners -contains $p.ProcessId) { continue }
        Write-Host "[清理] 残留的 $label 进程 PID $($p.ProcessId)" -ForegroundColor DarkYellow
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($listeners.Count -gt 1) {
        Write-Host "[警告] $label 有 $($listeners.Count) 个监听进程: $($listeners -join ', ')" -ForegroundColor Yellow
    }
}
# 只在显式要求(环境变量 AIFF_CLEAN=1)时才清理残留, 平时一条都不杀:
# 看门狗每隔几十秒就会调用本脚本, 若每次无脑清理, 一旦监听者查询抖动就可能把
# 正在服务的健康进程一起杀掉, 反而制造故障。默认只管「端口空着就拉起」。
if ($env:AIFF_CLEAN -eq '1') {
    Remove-Duplicates "uvicorn src.main:app" 8000 "后端 API"
    Remove-Duplicates "streamlit run frontend/main.py" 8501 "系统主入口"
    Remove-Duplicates "streamlit run frontend/main.py" 8502 "系统主入口(备用端口)"
    Remove-Duplicates "serve_console.py" 8591 "系统控制台"
    Start-Sleep -Seconds 1
}
# 1) 后端 API :8000
# 绑 0.0.0.0 而不是 127.0.0.1: 扫码登录时手机要能直接打开 API 上的确认页。
# 只影响本机所在局域网, 外部网络仍进不来(路由器不转发)。
if (Test-Port 8000) {
    Write-Host "[跳过] 8000 已在运行 (FastAPI 后端)" -ForegroundColor DarkGray
} else {
    Write-Host "[启动] 后端 API      -> http://127.0.0.1:8000/docs" -ForegroundColor Green
    Start-Process $psExe -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$root'; `$env:PYTHONIOENCODING='utf-8'; python -m uvicorn src.main:app --host 0.0.0.0 --port 8000"
    ) -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 2) 系统主入口 :8501 (统一入口: 一个应用, 按账号角色显示页面)
if (Test-Port 8501) {
    Write-Host "[跳过] 8501 已在运行 (系统主入口)" -ForegroundColor DarkGray
} else {
    Write-Host "[启动] 系统主入口    -> http://127.0.0.1:8501" -ForegroundColor Green
    Start-Process $psExe -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$root'; `$env:PYTHONIOENCODING='utf-8'; python -m streamlit run frontend/main.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false"
    ) -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 3) 备用端口 :8502 (同一个统一入口, 老链接 http://127.0.0.1:8502 仍然可用)
if (Test-Port 8502) {
    Write-Host "[跳过] 8502 已在运行 (系统主入口 · 备用端口)" -ForegroundColor DarkGray
} else {
    Write-Host "[启动] 备用端口      -> http://127.0.0.1:8502" -ForegroundColor Green
    Start-Process $psExe -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$root'; `$env:PYTHONIOENCODING='utf-8'; python -m streamlit run frontend/main.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false"
    ) -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 4) 系统控制台 :8591 (docs\console: 控制台首页 + 旧版 iframe 入口 portal.html)
if (Test-Port 8591) {
    Write-Host "[跳过] 8591 已在运行 (系统控制台)" -ForegroundColor DarkGray
} else {
    Write-Host "[启动] 系统控制台    -> http://127.0.0.1:8591" -ForegroundColor Green
    Start-Process $psExe -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$root'; python scripts/serve_console.py 8591"
    ) -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "等待服务就绪..." -ForegroundColor Cyan
Start-Sleep -Seconds 8
foreach ($p in 8000, 8501, 8502, 8591) {
    $url = if ($p -eq 8000) { "http://127.0.0.1:$p/docs" } elseif ($p -eq 8591) { "http://127.0.0.1:$p" } else { "http://127.0.0.1:$p/_stcore/health" }
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 6
        Write-Host ("  {0} : HTTP {1} OK" -f $p, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("  {0} : 未就绪(可能仍在启动)" -f $p) -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "访问地址(请用 127.0.0.1, 不要用 localhost):" -ForegroundColor Cyan
Write-Host "  系统控制台(14 页)     http://127.0.0.1:8591"
Write-Host "  旧版 iframe 入口      http://127.0.0.1:8591/portal.html"
Write-Host "  用户端               http://127.0.0.1:8501"
Write-Host "  管理后台             http://127.0.0.1:8502"
Write-Host "  API 文档             http://127.0.0.1:8000/docs"
Write-Host ""
Write-Host "停止服务: pwsh -File scripts\stop_all.ps1   (或任务管理器结束 python 进程)" -ForegroundColor DarkGray
