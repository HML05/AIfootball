# 停止本系统的全部服务(按端口查找并结束)
#
# 用法(项目根目录):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop_all.ps1
# 先停看门狗: 否则它 20 秒后会把刚停掉的服务又拉起来。
# 用命令行特征匹配, 而不是按名字杀所有 powershell(会误伤别的脚本)。
$pat = 'watch_' + 'services'
$me = $PID
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$pat*" -and $_.ProcessId -ne $me } |
    ForEach-Object {
        Write-Host "  看门狗 : 停止 PID $($_.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$ports = 8000, 8501, 8502, 8503, 8591
foreach ($p in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { Write-Host "  $p : 未运行" -ForegroundColor DarkGray; continue }
    foreach ($pid_ in ($conns.OwningProcess | Select-Object -Unique)) {
        $proc = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  $p : 停止 PID $pid_ ($($proc.ProcessName))" -ForegroundColor Yellow
            Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
        }
    }
}
Write-Host "完成。" -ForegroundColor Cyan
