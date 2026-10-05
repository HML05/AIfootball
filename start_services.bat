@echo off
chcp 65001 >nul
echo ============================================================
echo   足球数据分析与 AI 预测系统 - 一键启动全部服务
echo ============================================================
echo.
echo   完整演示(全部 14 页)  http://127.0.0.1:8591
echo   用户端(8 页)          http://127.0.0.1:8501
echo   管理后台(6 页)        http://127.0.0.1:8502
echo   API 文档              http://127.0.0.1:8000/docs
echo.
echo   每个服务各占一个窗口, 关闭窗口即停止该服务。
echo ------------------------------------------------------------
echo.

REM 绕过执行策略限制, 直接调用启动脚本
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_all.ps1"

echo.
pause
