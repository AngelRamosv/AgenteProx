@echo off
setlocal

:: CONFIGURACION
set "USUARIO=vix10"
set "PASSWORD=TU_CONTRASEÑA_AQUI"
set "ORIGEN=C:\Users\Desarrollo\Desktop\AgenteProxMox"
set "DESTINO_FINAL=Desktop\agent"

:: LISTA DE IPs (Separadas por espacio)
:: Agrega aqui todas las IPs de tus maquinas
set "MAQUINAS=192.168.49.109 192.168.49.76 192.168.49.151"

echo ==================================================
echo INICIANDO DESPLIEGUE MASIVO
echo ==================================================

for %%I in (%MAQUINAS%) do (
    echo.
    echo [PROCESANDO %%I]...
    
    :: 1. Conectar a la carpeta compartida administrativa (C$)
    net use \\%%I\c$ %PASSWORD% /u:%USUARIO% >nul 2>&1
    
    if %errorlevel% equ 0 (
        echo    - Conectado correctamente.
        
        :: 2. Crear carpeta si no existe
        if not exist "\\%%I\c$\Users\%USUARIO%\%DESTINO_FINAL%" (
            mkdir "\\%%I\c$\Users\%USUARIO%\%DESTINO_FINAL%"
        )
        
        :: 3. Copiar archivos (vm_agent.py y el .bat si lo tienes)
        echo    - Copiando archivos...
        copy /Y "%ORIGEN%\vm_agent.py" "\\%%I\c$\Users\%USUARIO%\%DESTINO_FINAL%\" >nul
        
        :: Si tienes un .bat deployado tambien descomenta esto:
        :: copy /Y "%ORIGEN%\iniciar_agente.bat" "\\%%I\c$\Users\%USUARIO%\%DESTINO_FINAL%\" >nul
        
        echo    - COPIA EXITOSA.
        
        :: 4. Desconectar
        net use \\%%I\c$ /delete >nul 2>&1
    ) else (
        echo    [ERROR] No se pudo conectar. Verifica:
        echo      1. IP correcta y encendida.
        echo      2. Usuario/Pass correctos.
        echo      3. Firewall permite compartir archivos.
    )
)

echo.
echo ==================================================
echo FIN DEL PROCESO
echo ==================================================
pause
