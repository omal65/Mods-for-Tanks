@echo off
setlocal
set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=1.0.0"

set "PY27EXE="
py -2.7 -c "print 'py27-ok'" >nul 2>&1
if not errorlevel 1 set "PY27EXE=py -2.7"
if not defined PY27EXE if exist "C:\Python27\python.exe" set "PY27EXE=C:\Python27\python.exe"

if not defined PY27EXE (
  echo [BUILD] Python 2.7 not found.
  pause
  exit /b 1
)

echo [BUILD] Python 2.7 found: %PY27EXE%
echo [BUILD] Building MarkBattle -> markbattle_%VERSION%.mtmod ...
echo.
%PY27EXE% build.py -v %VERSION%
echo.
pause