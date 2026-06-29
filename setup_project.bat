@echo off
echo.
echo ==========================================
echo   Lurnexa HRMS - DynamoDB Local Setup
echo ==========================================
echo.

:: 1. Check if DynamoDB is running
echo [1/3] Checking if DynamoDB is running on port 8001...
netstat -ano | findstr :8001 > nul
if %errorlevel% equ 0 (
    echo DynamoDB is already running.
) else (
    echo DynamoDB is NOT running. 
    echo Please run 'run_dynamodb.bat' in a separate window first!
    exit /b 1
)

:: 2. Initialize Tables
echo.
echo [2/3] Initializing DynamoDB Tables...
.\venv\Scripts\python.exe master_init.py
if %errorlevel% neq 0 (
    echo Error during table initialization.
    exit /b 1
)

:: 3. Success
echo.
echo [3/3] Setup Complete! 
echo Your project is now connected to Local DynamoDB.
echo You can now run the project using:
echo .\venv\Scripts\python.exe manage.py runserver
echo.
pause
