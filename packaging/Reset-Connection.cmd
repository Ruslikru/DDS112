@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Reset-Workstation.ps1" -Mode Connection
pause
