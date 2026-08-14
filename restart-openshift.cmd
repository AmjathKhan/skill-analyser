@echo off
rem Restart the OpenShift app without rebuilding (use after the 12-hour sandbox idle stop).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\openshift\deploy.ps1" -RestartOnly %*
