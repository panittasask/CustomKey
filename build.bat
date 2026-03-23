@echo off
echo ================================
echo  CustomKey - Build .exe
echo ================================

echo [1/2] Installing dependencies...
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo [2/2] Building .exe ...
pyinstaller --onefile --windowed --name CustomKey app.py

echo.
echo Done! Output: dist\CustomKey.exe
echo.
pause
