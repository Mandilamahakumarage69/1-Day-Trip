@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python virtual environment missing.
    echo In VS Code terminal run:
    echo   py -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    echo   .\.venv\Scripts\python.exe app.py create-admin
    pause
    exit /b 1
)
echo Open http://127.0.0.1:5000 in your browser.
echo Press Ctrl+C here to stop the server.
".venv\Scripts\python.exe" app.py
pause
