@echo off
echo CafeBot 시작 중...
cd /d "%~dp0"

pip install flask playwright pyperclip requests -q
playwright install chromium

python app.py
pause
