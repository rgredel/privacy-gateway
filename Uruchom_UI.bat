@echo off
setlocal
cd /d %~dp0
title Privacy Gateway - Bielik 11B
color 0b

echo ========================================================
echo        URUCHAMIANIE SERWERA UI (CHAINLIT)               
echo ========================================================
echo Model domyslny: Bielik 11B v2.3 (Replicate)
echo Srodowisko: .venv (Python 3.12)
echo ========================================================

if not exist ".venv\Scripts\python.exe" (
    echo [BLAD] Nie znaleziono srodowiska wirtualnego w katalogu .venv!
    pause
    exit /b
)

".venv\Scripts\python.exe" -m chainlit run app.py -w

pause