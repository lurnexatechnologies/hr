@echo off
set JAVA_EXE="%~dp0tools\jdk17\jdk-17.0.19+10\bin\java.exe"
set SPECIFIC_JAVA="%~dp0tools\jdk17\jdk-17.0.19+10\bin\java.exe"

if exist %SPECIFIC_JAVA% (
    set JAVA_EXE=%SPECIFIC_JAVA%
)

echo Starting DynamoDB Local on port 8001...
cd /d "%~dp0dynamodb_local"
%JAVA_EXE% -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb -port 8001
pause

