@echo off
setlocal DisableDelayedExpansion
set "PYTHONUTF8=1"
title LoRA Dataset Studio - move to V2
echo Close LDS and its launcher before continuing.
echo Extract this tool outside your LDS installation.
echo.
set /p "LDS_MIGRATION_ROOT=Existing LDS folder (paste its path): "
set "LDS_MIGRATION_ROOT=%LDS_MIGRATION_ROOT:"=%"
if not defined LDS_MIGRATION_ROOT goto cancelled
if not exist "%~dp0migrate_to_v2.py" goto missing
set "LDS_MIGRATION_PY="
for %%P in ("%LDS_MIGRATION_ROOT%\.venv\Scripts\python.exe" "%LDS_MIGRATION_ROOT%\env\Scripts\python.exe" "%LDS_MIGRATION_ROOT%\.python\python.exe" "%LDS_MIGRATION_ROOT%\python\python.exe") do (
  if not defined LDS_MIGRATION_PY if exist "%%~P" set "LDS_MIGRATION_PY=%%~P"
)
if defined LDS_MIGRATION_PY goto localpython
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if not errorlevel 1 goto pylauncher
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if not errorlevel 1 goto systempython
echo Python 3.10 or newer was not found. No installation files were changed.
goto failed
:localpython
"%LDS_MIGRATION_PY%" "%~dp0migrate_to_v2.py" --root "%LDS_MIGRATION_ROOT%"
goto result
:pylauncher
py -3 "%~dp0migrate_to_v2.py" --root "%LDS_MIGRATION_ROOT%"
goto result
:systempython
python "%~dp0migrate_to_v2.py" --root "%LDS_MIGRATION_ROOT%"
:result
if errorlevel 1 goto failed
echo.
pause
exit /b 0
:missing
echo Extract the complete migration ZIP first. migrate_to_v2.py is missing.
:failed
echo.
echo The migration did not finish. Read the message above before retrying.
pause
exit /b 1
:cancelled
echo Cancelled.
pause
exit /b 0
