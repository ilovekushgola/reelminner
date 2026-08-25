@echo off
REM Build the installer with Inno Setup 6.
REM Requires: ISCC.exe (winget install --id JRSoftware.InnoSetup -e)
setlocal
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo ERROR: ISCC.exe not found. Install Inno Setup 6 first:
    echo   winget install --id JRSoftware.InnoSetup -e
    exit /b 1
)
"%ISCC%" "%~dp0Reelminner.iss"
if errorlevel 1 exit /b 1
echo.
echo Installer built: dist\Reelminner-Setup.exe
endlocal
