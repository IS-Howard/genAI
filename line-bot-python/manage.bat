@echo off
setlocal EnableDelayedExpansion

:: ======================================
::   Line Bot - Project Management Script
:: ======================================

set "PROJECT_NAME=line-bot-python"
set "DB_VOLUME=%PROJECT_NAME%_postgres-data"
set "BACKUP_DIR=%cd%\backup"
set "BACKUP_FILE=%BACKUP_DIR%\db_storage_backup.tar.gz"

if "%~1"=="" goto usage

if /i "%~1"=="setup" goto setup
if /i "%~1"=="start" goto start
if /i "%~1"=="stop" goto stop
if /i "%~1"=="restart" goto restart
if /i "%~1"=="status" goto status
if /i "%~1"=="logs" goto logs
if /i "%~1"=="backup" goto backup
if /i "%~1"=="restore" goto restore

:usage
echo.
echo Usage: manage.bat [command]
echo.
echo Commands:
echo   setup    - Verify environment and create .env file
echo   start    - Start all services (docker-compose up -d)
echo   stop     - Stop all services (docker-compose down)
echo   restart  - Restart the application service
echo   status   - Show status of services
echo   logs     - Follow application logs
echo   backup   - Backup database volume to %BACKUP_FILE%
echo   restore  - Restore database volume from %BACKUP_FILE%
echo.
exit /b 0

:setup
echo.
echo [Setup] Verifying environment...
where docker >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not installed
    echo Please install Docker Desktop: https://www.docker.com/products/docker-desktop
    exit /b 1
)
docker ps >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not running
    echo Please start Docker Desktop and try again
    exit /b 1
)

if not exist ".env" (
    echo Creating .env from example...
    copy .env.example .env >nul
    echo Please edit .env and run setup again.
    start notepad .env
    exit /b 0
)

:: Verify .env has required variables
echo Verifying .env configuration...
set missing=0
findstr /R "^LINE_CHANNEL_SECRET=..*" .env >nul || set /a missing+=1
findstr /R "^LINE_CHANNEL_ACCESS_TOKEN=..*" .env >nul || set /a missing+=1
findstr /R "^GEMINI_API_KEY=..*" .env >nul || set /a missing+=1
findstr /R "^DB_PASSWORD=..*" .env >nul || set /a missing+=1

if %missing% GTR 0 (
    echo [ERROR] Some required variables are missing or empty in .env
    echo Please edit .env and set all required variables
    start notepad .env
    exit /b 1
)

echo [OK] Environment ready!
echo.
echo Starting services...
docker-compose up -d

echo.
echo Waiting for services to start...
timeout /t 5 /nobreak >nul

:: Check health
curl -s http://localhost:8000/ | findstr "ok" >nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Application is healthy
) else (
    echo [WARNING] Application may still be starting...
)

echo.
echo Setup completed successfully!
exit /b 0

:start
echo.
echo [Start] Starting services...
docker-compose up -d
exit /b %ERRORLEVEL%

:stop
echo.
echo [Stop] Stopping services...
docker-compose down
exit /b %ERRORLEVEL%

:restart
echo.
echo [Restart] Restarting application...
docker-compose restart line-bot
exit /b %ERRORLEVEL%

:status
echo.
echo [Status] Service status:
docker-compose ps
exit /b 0

:logs
echo.
echo [Logs] Following logs (Ctrl+C to exit):
docker-compose logs -f line-bot
exit /b 0

:backup
echo.
echo [Backup] Backing up database volume...
if not exist "%BACKUP_DIR%" (
    echo Creating backup directory %BACKUP_DIR%...
    mkdir "%BACKUP_DIR%"
)
docker run --rm ^
    -v "%DB_VOLUME%":/data ^
    -v "%BACKUP_DIR%":/backup ^
    alpine tar czf /backup/db_storage_backup.tar.gz -C /data .
if %ERRORLEVEL% EQU 0 (
    echo [OK] Backup saved to %BACKUP_FILE%
) else (
    echo [ERROR] Backup failed
)
exit /b %ERRORLEVEL%

:restore
echo.
echo [Restore] Restoring database volume...
if not exist "%BACKUP_FILE%" (
    echo [ERROR] Backup file not found: %BACKUP_FILE%
    exit /b 1
)
echo Warning: Current database data will be overwritten!
set /p confirm="Continue? (y/n): "
if /i not "!confirm!"=="y" exit /b 0

echo Stopping services...
docker-compose down
echo Removing old volume...
docker volume rm %DB_VOLUME% >nul 2>&1
echo Creating new volume...
docker volume create %DB_VOLUME% >nul
echo Restoring data...
docker run --rm ^
    -v "%DB_VOLUME%:/data" ^
    -v "%BACKUP_DIR%:/backup" ^
    alpine tar xzf /backup/db_storage_backup.tar.gz -C /data
if %ERRORLEVEL% EQU 0 (
    echo [OK] Restore successful
    docker-compose up -d
    echo.
    echo To verify the restore, run:
    echo   docker exec -it line-bot-db psql -U postgres -d line_bot -c "SELECT COUNT(*) FROM chat_history;"
) else (
    echo [ERROR] Restore failed
)
exit /b %ERRORLEVEL%
