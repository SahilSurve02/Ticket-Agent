@echo off
REM Quick Start Script for Streamlit UI
REM This script launches the IT Support Chatbot in your browser

echo.
echo ========================================
echo   IT Support Chatbot - Streamlit UI
echo ========================================
echo.
echo Starting the application...
echo.

REM Check if .env file exists
if not exist .env (
    echo WARNING: .env file not found!
    echo Please create a .env file with your OPENAI_API_KEY
    echo.
    pause
    exit /b 1
)

REM Run Streamlit using the virtual environment Python
D:\Ticket-Agent\.venv\Scripts\python.exe -m streamlit run app.py

pause
