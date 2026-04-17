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

REM Step 2: PyArmor 난독화
echo [2/5] PyArmor 코드 난독화...
pyarmor gen --output dist_obf -r main.py app.py config.py modules\__init__.py modules\license.py modules\browser.py modules\naver_auth.py modules\naver_post.py modules\naver_comment.py modules\adb_network.py modules\task_runner.py modules\txt_parser.py
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

REM Playwright 브라우저 복사
echo 브라우저 번들링 (약 400MB, 시간 소요)...
xcopy "%LOCALAPPDATA%\ms-playwright\chromium-1208" "dist\CafeBot\browsers\chromium-1208\" /E /I /Y >nul

echo.
echo ========================================
echo   빌드 완료! dist\CafeBot 폴더 확인
echo ========================================
echo.
pause
