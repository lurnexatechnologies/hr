# setup_project.ps1
# This script initializes the project with local DynamoDB.

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "  Lurnexa HRMS - DynamoDB Local Setup" -ForegroundColor Cyan
Write-Host "==========================================`n" -ForegroundColor Cyan

# 1. Check if DynamoDB is running
Write-Host "[1/3] Checking if DynamoDB is running on port 8001..." -ForegroundColor Yellow
$portCheck = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
if ($portCheck) {
    Write-Host "DynamoDB is running." -ForegroundColor Green
} else {
    Write-Host "DynamoDB is NOT running on port 8001." -ForegroundColor Red
    Write-Host "Please run 'run_dynamodb.bat' in a separate window first!" -ForegroundColor Cyan
    exit 1
}

# 2. Initialize Tables
Write-Host "`n[2/3] Initializing DynamoDB Tables..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" master_init.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error during table initialization." -ForegroundColor Red
    exit 1
}

# 3. Success
Write-Host "`n[3/3] Setup Complete!" -ForegroundColor Green
Write-Host "Your project is now connected to Local DynamoDB." -ForegroundColor White
Write-Host "`nYou can now run the project using:" -ForegroundColor Yellow
Write-Host ".\venv\Scripts\python.exe manage.py runserver" -ForegroundColor White
Write-Host ""
