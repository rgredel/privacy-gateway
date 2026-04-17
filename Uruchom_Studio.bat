@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title LangGraph Studio API Server
color 0d

echo ========================================================
echo        URUCHAMIANIE LANGGRAPH STUDIO API                
echo ========================================================
echo Tworzymy serwer dev dla interfejsu graficznego grafów...
echo Uzywane jest to samo zamkniete srodowisko (Python 3.12).
echo ========================================================

:: Aktywacja wirtualnego srodowiska
call .venv\Scripts\activate.bat

:: Uruchomienie serwera Studio, ktore automatycznie utworzy tunel i okno ze specyfikacja
langgraph dev

pause
