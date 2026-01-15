@echo off
:: Cambiar al directorio donde esta este archivo
cd /d "%~dp0"

:: Ejecutar el agente (Python debe estar en el PATH o usa la ruta completa si falla)
python vm_agent.py
