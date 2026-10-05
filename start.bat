@echo off
chcp 65001 >nul
echo ========================================
echo   足球数据分析系统 - 快速启动
echo ========================================
echo.

REM 检查虚拟环境
if not exist "venv\Scripts\activate.bat" (
    echo [1/4] 创建虚拟环境...
    python -m venv venv
)

echo [2/4] 激活虚拟环境并安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt -q

echo.
echo [3/4] 初始化数据（首次运行需要，下载五大联赛历史数据）...
choice /c YN /m "是否现在初始化数据"
if errorlevel 2 goto skip_init
python scripts\init_data.py
:skip_init

echo.
echo [4/4] 训练预测模型（首次运行需要）...
choice /c YN /m "是否现在训练模型"
if errorlevel 2 goto skip_train
python scripts\train_model.py
:skip_train

echo.
echo ========================================
echo   启动完成!
echo ========================================
echo.
echo 后端API:    uvicorn src.main:app --reload
echo 前端界面:   streamlit run frontend\app.py
echo API文档:    http://localhost:8000/docs
echo.
pause
