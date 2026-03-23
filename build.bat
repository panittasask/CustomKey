@echo off
echo ================================
echo  CustomKey - Build .exe
echo ================================

echo [1/2] Installing dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install pyinstaller

echo.
echo [2/2] Building .exe ...
.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name CustomKey app.py

echo.
echo Done! Output: dist\CustomKey.exe
echo.
pause
