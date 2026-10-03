@echo off
rem One-click: allow inbound TCP 8766 so your phone can reach the local demo.
rem Double-click this file and approve the UAC prompt.
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges, please click "Yes" in the UAC dialog...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="slowly-demo 8766" >nul 2>&1
netsh advfirewall firewall add rule name="slowly-demo 8766" dir=in action=allow protocol=TCP localport=8766

echo.
if %errorlevel% equ 0 (
  echo OK - port 8766 is now open for inbound connections.
  echo On your phone, open the http://<lan-ip>:8766 address shown in the frontend startup log.
) else (
  echo FAILED - could not add the firewall rule.
)
echo.
pause
