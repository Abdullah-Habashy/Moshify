@echo off
rem يبني WindowLayout.exe محليًا. محتاج بايثون متسطب.
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
echo == بنثبّت PyInstaller ==
python -m pip install --upgrade pip pyinstaller || goto :fail
echo == بنبني ==
python -m PyInstaller build\WindowLayout.spec --noconfirm --clean || goto :fail
echo.
echo تمام. الملف جاهز هنا:
echo    %CD%\dist\WindowLayout.exe
pause
exit /b 0
:fail
echo.
echo البناء فشل. ابعت آخر رسالة خطأ فوق.
pause
exit /b 1
