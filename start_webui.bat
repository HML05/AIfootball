@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================================
echo   足球数据分析与 AI 预测系统 (新版界面 + 真实数据)
echo ============================================================
echo.
echo   界面入口    http://127.0.0.1:8000/
echo   接口文档    http://127.0.0.1:8000/docs
echo   数据来源    data\database\football.db  (12,698 场比赛 / 4,745 名球员)
echo.
echo   首次运行或前端改过代码时，先执行: python scripts\build_webui.py
echo ------------------------------------------------------------
echo.

set PYTHON=C:\Python313\python.exe
if not exist "%PYTHON%" set PYTHON=python

if not exist "webui\dist\index.html" (
  echo [1/2] 未发现前端构建产物，正在构建（约 30 秒）...
  "%PYTHON%" scripts\build_webui.py || goto :err
) else (
  echo [1/2] 已发现前端构建产物，跳过构建（需要重建请运行 python scripts\build_webui.py）
)

echo [2/2] 启动服务 http://127.0.0.1:8000/ ...
"%PYTHON%" -m uvicorn src.main:app --host 127.0.0.1 --port 8000
goto :eof

:err
echo.
echo [x] 构建失败，请查看上面的错误信息。
pause
