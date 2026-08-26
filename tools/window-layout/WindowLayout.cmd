@echo off
rem يفتح واجهة البرنامج. لو بايثون مش متسطب، حمّله من python.org
setlocal
set "HERE=%~dp0"
where pythonw.exe >nul 2>&1 && (
  start "" pythonw.exe "%HERE%WindowLayout.pyw"
  exit /b 0
)
py -3 --version >nul 2>&1 && (
  start "" pyw -3 "%HERE%WindowLayout.pyw"
  exit /b 0
)
echo بايثون مش متسطب على الجهاز.
echo حمّله من https://www.python.org/downloads/windows/ وافتكر تعلّم "Add python.exe to PATH".
pause
