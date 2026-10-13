@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating project virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 goto error
call ".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 goto error
goto end
:error
echo.
echo Dashboard startup failed. Review the error above.
pause
exit /b 1
:end
endlocal
