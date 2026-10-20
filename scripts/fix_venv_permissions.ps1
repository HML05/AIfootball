# Fix the integrity level of the vision virtualenv (and the folders it must write to).
#
# Why this is needed
# ------------------
# .venv-vision\Scripts\python.exe was created by a low-integrity tool process, so the
# whole tree carries a "Low Mandatory Level" label. Windows starts that interpreter as a
# LOW integrity process, and a low-integrity process may not write to MEDIUM integrity
# files -- so it fails with
#     PermissionError: [Errno 13] Permission denied: 'data\vision\calib\v2.json'
# even though the same folder is writable by the system Python. Raising a label needs
# SeRelabelPrivilege, i.e. an elevated prompt, which is why this script re-launches itself
# as administrator.
#
# Usage: right click -> "Run with PowerShell", or
#        powershell -ExecutionPolicy Bypass -File scripts\fix_venv_permissions.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host '需要管理员权限：正在请求提权（会弹一个 UAC 窗口）...' -ForegroundColor Yellow
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    Start-Process -FilePath 'powershell.exe' -ArgumentList $args -Verb RunAs | Out-Null
    return
}

$targets = @(
    (Join-Path $root '.venv-vision'),
    (Join-Path $root 'data'),
    (Join-Path $root 'models')
) | Where-Object { Test-Path $_ }

foreach ($t in $targets) {
    Write-Host "[..] $t" -ForegroundColor Cyan
    $out = & icacls $t /setintegritylevel '(OI)(CI)M' /T /C /Q 2>&1
    $bad = ($out | Select-String 'Failed processing').Count
    if ($bad -gt 0) { Write-Host "     [!] 有文件处理失败：$($out[-1])" -ForegroundColor Yellow }
}

$py = Join-Path $root '.venv-vision\Scripts\python.exe'
if (Test-Path $py) {
    Write-Host ''
    Write-Host '[..] 验证：用 .venv-vision 的解释器往 data\vision\calib 写一个临时文件' -ForegroundColor Cyan
    $probe = Join-Path $root 'data\vision\calib\_integrity_probe.txt'
    New-Item -ItemType Directory -Force -Path (Split-Path $probe) | Out-Null
    & $py -c "import sys; open(sys.argv[1], 'w').write('ok'); print('write ok')" $probe
    if ($LASTEXITCODE -eq 0) {
        Remove-Item $probe -Force -ErrorAction SilentlyContinue
        Write-Host '[ok] 修好了：现在可以直接双击 scripts\vision_calibrate.bat' -ForegroundColor Green
    } else {
        Write-Host '[x] 仍然写不进去，请把上面的报错发给我' -ForegroundColor Red
    }
}

Write-Host ''
Read-Host '按回车关闭'
