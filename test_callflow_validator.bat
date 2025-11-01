@echo off
REM Batch script to test the callflow validator with debug logging on test server

set SERVER=69.39.69.102
set USER=123net

echo ====================================================================
echo Testing CallFlow Validator with Debug Logging
echo ====================================================================
echo.
echo NOTE: You will be prompted for the SSH password: dH10oQW6jQ2rc^&402B%%e
echo.

REM Upload the updated callflow validator
echo Uploading updated callflow_validator.py...
scp freepbx-tools\bin\callflow_validator.py %USER%@%SERVER%:/tmp/callflow_validator.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to upload callflow_validator.py
    exit /b 1
)
echo Upload successful
echo.

REM Test the validator with debug logging
echo Testing callflow validator with debug logging...
echo Command: python3 /tmp/callflow_validator.py 2485815200 --debug
echo.

ssh %USER%@%SERVER% "cd /tmp && python3 callflow_validator.py 2485815200 --debug"

echo.
echo ====================================================================
echo Checking debug log file...
echo ====================================================================
ssh %USER%@%SERVER% "ls -la /tmp/callflow_validator.log && echo '--- Log Contents (last 20 lines) ---' && tail -20 /tmp/callflow_validator.log"

echo.
echo ====================================================================
echo Test Complete!
echo ====================================================================
