@echo off
chcp 65001 >nul
echo ========================================
echo   CafeBot Build Pipeline
echo ========================================
echo.

cd /d "%~dp0\.."

REM Step 1: 이전 빌드 정리
echo [1/5] 이전 빌드 정리...
if exist dist rmdir /s /q dist
if exist build_temp rmdir /s /q build_temp
if exist dist_obf rmdir /s /q dist_obf

REM Step 2: PyArmor 난독화 (modules 폴더 통째로 전달해 하위구조 보존)
echo [2/5] PyArmor 코드 난독화...
pyarmor gen --output dist_obf -r main.py app.py config.py modules
if errorlevel 1 (
    echo 오류: PyArmor 난독화 실패
    pause
    exit /b 1
)

REM Step 3: 비-Python 파일 복사
echo [3/5] 리소스 파일 복사...
xcopy templates dist_obf\templates\ /E /I /Y >nul
mkdir dist_obf\adb 2>nul
copy "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" dist_obf\adb\ >nul
copy "%LOCALAPPDATA%\Android\Sdk\platform-tools\AdbWinApi.dll" dist_obf\adb\ >nul
copy "%LOCALAPPDATA%\Android\Sdk\platform-tools\AdbWinUsbApi.dll" dist_obf\adb\ >nul

REM Step 4: PyInstaller 빌드
echo [4/5] PyInstaller exe 빌드 (시간 소요)...
pyinstaller build\cafebot.spec --noconfirm
if errorlevel 1 (
    echo 오류: PyInstaller 빌드 실패
    pause
    exit /b 1
)

REM Step 5: 외부 data 폴더 + adb + browsers 복사
echo [5/5] 배포 폴더 구성...
mkdir dist\CafeBot\data 2>nul
echo {"mains":[],"commenters":[]} > dist\CafeBot\data\accounts.json
xcopy dist_obf\adb dist\CafeBot\adb\ /E /I /Y >nul

REM Playwright 브라우저 복사 (chromium + headless_shell 둘 다 필수)
echo 브라우저 번들링 (약 450MB, 시간 소요)...
xcopy "%LOCALAPPDATA%\ms-playwright\chromium-1208" "dist\CafeBot\browsers\chromium-1208\" /E /I /Y >nul
xcopy "%LOCALAPPDATA%\ms-playwright\chromium_headless_shell-1208" "dist\CafeBot\browsers\chromium_headless_shell-1208\" /E /I /Y >nul

REM Step 6: Inno Setup 인스톨러 생성
echo [6/6] Inno Setup 인스톨러 빌드...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo 경고: Inno Setup 미설치 - 인스톨러 생략
    goto :END
)
%ISCC% build\installer.iss
if errorlevel 1 (
    echo 오류: Inno Setup 빌드 실패
    pause
    exit /b 1
)

:END
echo.
echo ========================================
echo   빌드 완료!
echo   - 실행 폴더: dist\CafeBot
echo   - 인스톨러 : installer_output\CafeBot_Setup_v1.6.exe
echo ========================================
echo.
pause
