<#
.SYNOPSIS
    一次性搭好 YOLOv8 视觉模块的独立环境：Python 3.12 + torch(CUDA) + ultralytics。

.DESCRIPTION
    与主应用隔离：装到 .venv-vision，不动系统 Python（主应用和 CI 都用它）。
    torch 走 CUDA 12.1 的官方 index；显卡驱动 546.30 对应 CUDA 12.2，向下兼容没问题。
    机器上没有 NVIDIA 显卡时用 -Cpu，装 CPU 版（慢，但能跑通流程）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\vision_setup.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\vision_setup.ps1 -Cpu
#>
[CmdletBinding()]
param(
    [string]$Venv = ".venv-vision",
    [string]$CudaIndex = "https://download.pytorch.org/whl/cu121",
    [switch]$Cpu
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = Join-Path $root "$Venv\Scripts\python.exe"

    if (-not (Test-Path $python)) {
        Write-Host "=== [1/4] 建虚拟环境 $Venv ===" -ForegroundColor Cyan
        $created = $false
        # 首选 py 启动器；本机 py -3.12 认不到 uv 管理的 3.12，所以还要兜底
        foreach ($candidate in @(
                @{ exe = "py"; args = @("-3.12", "-m", "venv", $Venv) },
                @{ exe = "py"; args = @("-3.11", "-m", "venv", $Venv) }
            )) {
            try {
                & $candidate.exe @($candidate.args) 2>$null
                if (Test-Path $python) { $created = $true; break }
            }
            catch { }
        }
        if (-not $created) {
            # 兜底 1：uv 管理的 CPython
            $uvPy = Get-ChildItem "$env:APPDATA\uv\python\cpython-3.1*\python.exe" -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -First 1
            if ($uvPy) {
                Write-Host "  用 uv 的 Python：$($uvPy.FullName)"
                & $uvPy.FullName -m venv $Venv
                $created = Test-Path $python
            }
        }
        if (-not $created) {
            # 兜底 2：PATH 里的 python（版本可能不是 3.12，ultralytics 对 3.9+ 都支持）
            $sysPy = (Get-Command python -ErrorAction SilentlyContinue).Source
            if ($sysPy) {
                Write-Host "  用 PATH 里的 python：$sysPy" -ForegroundColor Yellow
                & $sysPy -m venv $Venv
            }
        }
        if (-not (Test-Path $python)) {
            throw "建环境失败：装一个 Python 3.10~3.12 后重跑（https://www.python.org/downloads/）"
        }
    }
    else {
        Write-Host "=== [1/4] 复用已有环境 $Venv ===" -ForegroundColor Cyan
    }

    Write-Host "=== [2/4] 升级 pip ===" -ForegroundColor Cyan
    & $python -m pip install --upgrade pip

    $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
    Write-Host "=== [3/4] 装 torch / torchvision ===" -ForegroundColor Cyan
    if ($Cpu) {
        & $python -m pip install torch torchvision
    }
    else {
        & $python -m pip install --index-url $CudaIndex torch torchvision
    }

    Write-Host "=== [4/4] 装 ultralytics + lap ===" -ForegroundColor Cyan
    # torch 上一步已装好，这里按 requirements-vision.txt 补齐其余依赖（已满足的会跳过）
    & $python -m pip install -r requirements-vision.txt

    Write-Host "`n=== 自检 ===" -ForegroundColor Cyan
    & $python -c "import torch;print('torch', torch.__version__);print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '(未检测到 GPU)')"
    & $python -c "import ultralytics, sys;print('ultralytics', ultralytics.__version__);print('python', sys.version.split()[0])"

    Write-Host "`n环境就绪。下一步：" -ForegroundColor Green
    Write-Host "  .\scripts\vision_setup.ps1 之后，用这个解释器跑脚本："
    Write-Host "  $Venv\Scripts\python.exe scripts\vision_smoke.py --demo"
}
finally {
    Pop-Location
}
