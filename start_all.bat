@echo off
chcp 65001 >nul
echo ============================================
echo   Simple Federated - Procurement AI Tool
echo   (Federated DB: KIMDIS + TED/ENDORSE)
echo ============================================
echo.

echo [1/3] Starting Backend (Flask API - port 5051)...
start cmd /k "chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && cd /d %~dp0backend && python core/server.py"

timeout /t 3 >nul

echo [2/3] Starting Frontend (React - port 5174)...
start cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 3 >nul

echo [3/3] Opening browser...
start http://localhost:5174

echo.
echo ============================================
echo   All services started!
echo   Frontend: http://localhost:5174
echo   Backend:  http://localhost:5051
echo   Neo4j DB: federated (http://localhost:7474)
echo   Models:   models/ (local)
echo ============================================

exit
