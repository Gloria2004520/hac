@echo off
rem One-click: remove the inbound TCP 8766 rule again after the demo.
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges, please click "Yes" in the UAC dialog...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="slowly-demo 8766"

echo.
if %errorlevel% equ 0 (
  echo OK - the firewall rule for port 8766 has been removed.
) else (
  echo Note - no rule named "slowly-demo 8766" was found.
)
echo.
pause
