@echo off
setlocal

if "%~1"=="" (
    echo [ERROR] Missing venv folder argument.
    echo Usage: run_py.bat ^<venv_dir^> ^<python args...^>
    exit /b 2
)

set "VENV_DIR=%~1"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

shift

if "%~1"=="" (
    echo [ERROR] Missing python arguments.
    echo Usage: run_py.bat ^<venv_dir^> ^<python args...^>
    exit /b 2
)

if exist "%PYTHON_EXE%" (
    call "%PYTHON_EXE%" %*
) else (
    call py -3 %*
)

set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
