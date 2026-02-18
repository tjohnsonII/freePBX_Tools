@echo off
setlocal

if "%~1"=="" (
    echo [ERROR] Missing venv folder argument.
    echo Usage: run_py.bat ^<venv_folder_name^> ^<script_path^> [args...]
    exit /b 2
)

if "%~2"=="" (
    echo [ERROR] Missing script/module argument.
    echo Usage: run_py.bat ^<venv_folder_name^> ^<script_path^> [args...]
    exit /b 2
)

set "VENV_FOLDER=%~1"
set "ENTRYPOINT=%~2"
set "VENV_PY=%VENV_FOLDER%\Scripts\python.exe"

shift
shift

if exist "%VENV_PY%" (
    call "%VENV_PY%" "%ENTRYPOINT%" %*
) else (
    call py -3 "%ENTRYPOINT%" %*
)

set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
