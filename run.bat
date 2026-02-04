@echo off
cd /d "%~dp0"
python\python.exe -m streamlit run app.py --server.headless true --server.port 8501
pause
