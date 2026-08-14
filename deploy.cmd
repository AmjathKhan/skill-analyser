@echo off
rem Rebuild and roll out AI Skill Analyser to the OpenShift Developer Sandbox.
rem First log in with the oc login command from the OpenShift console (User -> Copy login command).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\openshift\deploy.ps1" %*
