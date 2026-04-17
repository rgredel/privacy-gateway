@echo off
title Uruchamianie Privacy Gateway (Chainlit w Python 3.12)
color 0b

echo ========================================================
echo        URUCHAMIANIE SERWERA UI (CHAINLIT)               
echo ========================================================
echo Pomyślnie użyto stabilnego środowiska Python 3.12!
echo Ominięto błędy kompatybilności wersji eksperymentalnych.
echo Przeglądarka powinna otworzyć się za chwilę automatycznie.
echo Jeśli tak się nie stanie, wejdź na: http://localhost:8000
echo ========================================================

:: Aktywacja dedykowanego środowiska, zainstalowanego w locie
call .venv\Scripts\activate.bat

:: Uruchomienie bezpiecznego środowiska po "sprzątaniu"
chainlit run app.py -w

pause
