# install_dynamodb.ps1
# This script downloads and sets up DynamoDB Local in the 'dynamodb_local' folder.

$installDir = "dynamodb_local"
$zipFile = "dynamodb_local_latest.zip"
$downloadUrl = "https://s3.us-west-2.amazonaws.com/dynamodb-local/dynamodb_local_latest.zip"

# Create directory if it doesn't exist
if (!(Test-Path $installDir)) {
    Write-Host "Creating directory $installDir..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $installDir
}

# Download DynamoDB Local
Write-Host "Downloading DynamoDB Local from $downloadUrl..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipFile

# Extract the zip file
Write-Host "Extracting files to $installDir..." -ForegroundColor Cyan
Expand-Archive -Path $zipFile -DestinationPath $installDir -Force

# Clean up
Write-Host "Cleaning up zip file..." -ForegroundColor Cyan
Remove-Item -Path $zipFile

Write-Host "DynamoDB Local has been installed successfully in the '$installDir' folder." -ForegroundColor Green
Write-Host "You can now run it using 'run_dynamodb.bat'." -ForegroundColor Yellow
