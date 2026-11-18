@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "DIR=%~dp0"
set "runner=python"
where python >nul 2>&1 && python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && goto run
set "runner=python3"
where python3 >nul 2>&1 && python3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && goto run
set "runner=py -3"
where py >nul 2>&1 && py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && goto run
echo ERROR: need Python 3.9 or newer as python, python3 or py -3 on PATH. 1>&2
exit /b 2

:run
%runner% "%DIR%ws.py" %*
exit /b %errorlevel%
