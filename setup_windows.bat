@echo off
echo ============================================================
echo  AUTONOMOUS PENTEST AGENT - Windows Setup
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

:: Check Ollama
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Ollama not found. Install from https://ollama.ai
    pause
    exit /b 1
)
echo [OK] Ollama found

:: Create directories
mkdir memory 2>nul
mkdir logs 2>nul
mkdir knowledge 2>nul
echo [OK] Directories created

:: Install dependencies
echo.
echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo Checking if Qwen 2.5:7B is pulled...
ollama list | findstr "qwen2.5:7b" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Pulling qwen2.5:7b (this may take a while ~4GB)...
    ollama pull qwen2.5:7b
) else (
    echo [OK] qwen2.5:7b already available
)

echo.
echo ============================================================
echo  Setup complete!
echo.
echo  NEXT STEPS:
echo  1. Start DVWA:
echo     docker run -d -p 80:80 vulnerables/web-dvwa
echo     OR use XAMPP + DVWA at localhost/dvwa
echo.
echo  2. Make sure Ollama is running:
echo     ollama serve
echo.
echo  3. Run the agent:
echo     python orchestrator.py
echo ============================================================
pause
