@echo off
setlocal

set "KDI_REPO_ROOT=%~dp0.."
set "KDI_RUNTIME_DIR=%KDI_REPO_ROOT%\.kdi-runtime"
set "KDI_POINTER=%KDI_RUNTIME_DIR%\current-release.txt"
set "KDI_APP_DIR=%KDI_REPO_ROOT%\dashboard"
if exist "%KDI_POINTER%" set /p KDI_APP_DIR=<"%KDI_POINTER%"
set "KDI_LOG_DIR=%KDI_RUNTIME_DIR%\logs"
set "KDI_LOG_FILE=%KDI_LOG_DIR%\kdi-media-library.log"

if not exist "%KDI_APP_DIR%\package.json" (
  echo KDI startup failed: package.json is missing from "%KDI_APP_DIR%". 1>&2
  exit /b 2
)
if not exist "%KDI_APP_DIR%\.env.local" (
  echo KDI startup failed: .env.local is missing from "%KDI_APP_DIR%". 1>&2
  exit /b 3
)
if not exist "%KDI_APP_DIR%\.next\BUILD_ID" (
  echo KDI startup failed: verified production build is missing from "%KDI_APP_DIR%". 1>&2
  exit /b 4
)
if not exist "%KDI_APP_DIR%\.kdi-candidate-verified.json" if exist "%KDI_POINTER%" (
  echo KDI startup failed: active release has no verification manifest. 1>&2
  exit /b 6
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo KDI startup failed: npm.cmd is not available on PATH. 1>&2
  exit /b 5
)

if not exist "%KDI_LOG_DIR%" mkdir "%KDI_LOG_DIR%"
cd /d "%KDI_APP_DIR%"
for %%I in ("%KDI_APP_DIR%\..") do set "KDI_RELEASE_ID=%%~nxI"
echo [%date% %time%] Starting KDI Media Library release %KDI_RELEASE_ID% on http://127.0.0.1:3000>>"%KDI_LOG_FILE%"
call npm.cmd start >>"%KDI_LOG_FILE%" 2>&1
set "KDI_EXIT_CODE=%errorlevel%"
echo [%date% %time%] KDI Media Library stopped with exit code %KDI_EXIT_CODE%.>>"%KDI_LOG_FILE%"
exit /b %KDI_EXIT_CODE%
