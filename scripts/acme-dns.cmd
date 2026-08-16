@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0acme-dns.ps1" %*
