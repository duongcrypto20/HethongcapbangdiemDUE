@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv (
  echo Dang tao moi truong ao Python...
  python -m venv .venv
)
call .venv\Scripts\activate
pip install -q -r requirements.txt
echo Mo trinh duyet tai http://127.0.0.1:5000
start "" http://127.0.0.1:5000
python app.py
