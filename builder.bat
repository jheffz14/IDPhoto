@echo off
setlocal EnableDelayedExpansion

title ID Photo App - Builder and Deployer
echo ============================================================
echo   ID Photo App - Windows Setup and Deploy
echo ============================================================
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Download from https://www.python.org/downloads/
    echo         Tick "Add Python to PATH" during install, then re-run this file.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] %PYVER% detected.

:: ── Move to script folder ─────────────────────────────────────────────────────
cd /d "%~dp0"
echo [INFO] Working directory: %CD%

:: ── Create virtual environment ────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo [STEP 1/5] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

:: ── Activate venv ─────────────────────────────────────────────────────────────
call venv\Scripts\activate.bat
echo [OK] Virtual environment activated.

:: ── Install dependencies ──────────────────────────────────────────────────────
echo.
echo [STEP 2/5] Installing dependencies (this may take a minute)...
echo.

python -m pip install --upgrade pip
if errorlevel 1 ( echo [WARN] pip upgrade failed, continuing anyway... )

echo   Installing flask...
pip install flask
if errorlevel 1 ( echo [ERROR] Failed to install flask & pause & exit /b 1 )

echo   Installing werkzeug...
pip install werkzeug
if errorlevel 1 ( echo [ERROR] Failed to install werkzeug & pause & exit /b 1 )

echo   Installing pillow...
pip install pillow
if errorlevel 1 ( echo [ERROR] Failed to install pillow & pause & exit /b 1 )

echo   Installing numpy...
pip install numpy
if errorlevel 1 ( echo [ERROR] Failed to install numpy & pause & exit /b 1 )

echo   Installing opencv-python...
pip install opencv-python
if errorlevel 1 ( echo [ERROR] Failed to install opencv-python & pause & exit /b 1 )

echo   Installing reportlab...
pip install reportlab
if errorlevel 1 ( echo [ERROR] Failed to install reportlab & pause & exit /b 1 )

echo   Installing pyinstaller...
pip install pyinstaller
if errorlevel 1 ( echo [ERROR] Failed to install pyinstaller & pause & exit /b 1 )

echo.
echo [OK] All dependencies installed.

:: ── Create required folders ───────────────────────────────────────────────────
echo.
echo [STEP 3/5] Setting up folders and config...

if not exist "data"             mkdir "data"
if not exist "static\uploads"  mkdir "static\uploads"
if not exist "static\outputs"  mkdir "static\outputs"
if not exist "templates"       mkdir "templates"
echo [OK] Folders ready.

:: ── Write default config.json if missing ─────────────────────────────────────
if not exist "data\config.json" (
    echo Writing default config.json...
    (
        echo {
        echo   "app": {
        echo     "title": "ID Photo Studio",
        echo     "output_dpi": 300,
        echo     "upload_max_mb": 20
        echo   },
        echo   "admin": {
        echo     "username": "admin",
        echo     "password": "admin123",
        echo     "session_secret": "change-me-in-production"
        echo   },
        echo   "paper_sizes": {
        echo     "a4":     { "name": "A4",           "width_mm": 210,   "height_mm": 297   },
        echo     "letter": { "name": "Letter",        "width_mm": 215.9, "height_mm": 279.4 },
        echo     "4r":     { "name": "4R (4x6 inch)", "width_mm": 101.6, "height_mm": 152.4 }
        echo   },
        echo   "photo_sizes": {
        echo     "2x2": {
        echo       "name": "2x2 inch (US Visa)",
        echo       "width_mm": 50.8, "height_mm": 50.8,
        echo       "background_color": "#ffffff", "enabled": true
        echo     },
        echo     "35x45": {
        echo       "name": "35x45mm (EU Passport)",
        echo       "width_mm": 35, "height_mm": 45,
        echo       "background_color": "#ffffff", "enabled": true
        echo     }
        echo   },
        echo   "packages": {
        echo     "pkg_basic": {
        echo       "name": "Basic Pack (8 photos)",
        echo       "description": "8 passport-size photos on A4",
        echo       "enabled": true,
        echo       "paper_size": "a4",
        echo       "orientation": "portrait",
        echo       "margin_mm": 5,
        echo       "spacing_mm": 3,
        echo       "show_cut_lines": true,
        echo       "background_color": "#ffffff",
        echo       "items": [
        echo         { "photo_size_id": "35x45", "quantity": 8 }
        echo       ]
        echo     }
        echo   }
        echo }
    ) > "data\config.json"
    echo [OK] config.json created.  Default login: admin / admin123
) else (
    echo [OK] config.json already exists, keeping your settings.
)

:: ── Locate the OpenCV cascade data folder ────────────────────────────────────
:: This is the key fix: we must tell PyInstaller to bundle the cascade XML.
echo.
echo [STEP 4/5] Locating OpenCV cascade data for bundling...

for /f "delims=" %%i in ('python -c "import cv2, os; print(os.path.dirname(cv2.data.haarcascades.rstrip(chr(47)+chr(92))))"') do set CV2_DATA=%%i
if not defined CV2_DATA (
    echo [ERROR] Could not locate cv2 data folder. Check your OpenCV install.
    pause
    exit /b 1
)
echo [OK] cv2 data folder: %CV2_DATA%

:: ── Build executable with PyInstaller ────────────────────────────────────────
echo.
echo [STEP 5/5] Building standalone executable into dist\ folder...
echo             (This will take 1-3 minutes, please wait)
echo.

pyinstaller --noconfirm --onedir --console ^
    --name "IDPhotoApp" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "data;data" ^
    --add-data "image_processor.py;." ^
    --add-data "%CV2_DATA%;cv2/data" ^
    --hidden-import "flask" ^
    --hidden-import "werkzeug" ^
    --hidden-import "PIL" ^
    --hidden-import "cv2" ^
    --hidden-import "numpy" ^
    --hidden-import "reportlab" ^
    --hidden-import "reportlab.pdfgen" ^
    --hidden-import "reportlab.lib.utils" ^
    app.py

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. See error above.
    pause
    exit /b 1
)

:: ── Copy runtime data into dist ───────────────────────────────────────────────
echo.
echo Copying runtime data to dist\IDPhotoApp\...

if not exist "dist\IDPhotoApp\data"            mkdir "dist\IDPhotoApp\data"
if not exist "dist\IDPhotoApp\static\uploads"  mkdir "dist\IDPhotoApp\static\uploads"
if not exist "dist\IDPhotoApp\static\outputs"  mkdir "dist\IDPhotoApp\static\outputs"

copy /Y "data\config.json"  "dist\IDPhotoApp\data\config.json"  >nul
xcopy /E /I /Y "templates"  "dist\IDPhotoApp\templates"         >nul
xcopy /E /I /Y "static"     "dist\IDPhotoApp\static"            >nul

echo.
echo ============================================================
echo   BUILD COMPLETE!
echo.
echo   Executable:  dist\IDPhotoApp\IDPhotoApp.exe
echo.
echo   To run:  open dist\IDPhotoApp\ and double-click IDPhotoApp.exe
echo   To share: zip the entire dist\IDPhotoApp\ folder.
echo             No Python needed on the target machine.
echo ============================================================
echo.

set /p LAUNCH="Launch the app now? (Y/N): "
if /i "%LAUNCH%"=="Y" (
    echo Starting IDPhotoApp.exe...
    start "" "dist\IDPhotoApp\IDPhotoApp.exe"
)

deactivate
pause
