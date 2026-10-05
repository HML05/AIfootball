@echo off
chcp 65001 >nul
echo ========================================
echo   足球分析系统 - 管理员后台
echo ========================================
echo.
echo 启动管理员后台 (端口 8502)...
echo 访问地址: http://localhost:8502
echo.
echo 功能模块:
echo   1. 数据概览 - 各表数据量与系统状态
echo   2. 数据浏览 - 查看数据库各表数据
echo   3. API接口测试 - 测试后端FastAPI接口
echo   4. 数据库管理 - SQL查询/表结构/备份
echo   5. 数据更新控制 - 配置API Key/导入数据
echo   6. 模型管理 - 查看模型/触发重训
echo.
echo 按 Ctrl+C 停止服务
echo ========================================
echo.

cd /d "%~dp0"
python -m streamlit run frontend\admin.py --server.port 8502 --server.headless true

pause
