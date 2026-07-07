@echo off
setlocal
cd /d "%~dp0"

if not exist venv (
    echo Luodaan virtuaaliymparisto...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Tarkistetaan riippuvuudet...
pip install -r requirements.txt -q

echo Kaynnistetaan SMS Pate...
streamlit run Etusivu.py

pause
