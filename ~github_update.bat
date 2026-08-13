@echo off
chcp 65001 >nul
title GitHub Uploader - artnp/Jobboard_Fastwork
echo.
echo ========================================
echo   Uploading to artnp/Jobboard_Fastwork (main)
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Github\github_upload.ps1" "%~dp0." "artnp/Jobboard_Fastwork"

if %ERRORLEVEL% equ 0 (
    echo.
    echo Upload complete!
) else (
    echo.
    echo Upload had errors.
)
echo.
exit /b
