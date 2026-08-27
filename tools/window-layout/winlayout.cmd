@echo off
rem سطر الأوامر:  winlayout save "اسم"  /  winlayout restore "اسم"  /  winlayout list
setlocal
chcp 65001 >nul
set "HERE=%~dp0"
where python.exe >nul 2>&1 && (
  python.exe "%HERE%WindowLayout.py" %*
  exit /b %errorlevel%
)
py -3 "%HERE%WindowLayout.py" %*
