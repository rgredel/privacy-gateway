@echo off
setlocal
cd /d %~dp0
set PYTHONIOENCODING=utf-8
title Privacy Gateway - LangGraph Studio
color 0d

echo ========================================================
echo        URUCHAMIANIE LANGGRAPH STUDIO API                
echo ========================================================
echo Tworzymy serwer dev dla interfejsu graficznego grafow...
echo Srodowisko: .venv (Python 3.12)
echo ========================================================

if not exist ".venv\Scripts\langgraph.exe" (
    echo [BLAD] Nie znaleziono langgraph.exe w .venv\Scripts!
    pause
    exit /b
)

".venv\Scripts\langgraph.exe" dev

pause