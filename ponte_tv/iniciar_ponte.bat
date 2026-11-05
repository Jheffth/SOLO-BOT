@echo off
rem Abre a ponte da TV minimizada. Para iniciar com o Windows, ponha um atalho
rem deste arquivo em shell:startup (Win + R, digite shell:startup).
cd /d "%~dp0"
start "Ponte da TV" /min python ponte.py
