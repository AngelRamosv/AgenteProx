import requests
import subprocess
import platform
import time
import re
import config
import teams_bot
import random

def is_pingable(ip):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    cmd = ['ping', param, '1', ip]
    try:
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except:
        return False

def check_process_via_agent(ip):
    url = f"http://{ip}:{config.AGENT_PORT}/status"
    no_proxy = {"http": None, "https": None}

    try:
        response = requests.get(url, timeout=config.AGENT_TIMEOUT, proxies=no_proxy)
        if response.status_code == 200:
            data = response.json()
            procs = data.get("procesos", [])
            if procs:
                return "activo", f"Activo ({', '.join(procs)})"
            else:
                return "sin_proceso", "Sin procesos RPA corriendo"
        return "error_status", "Agente responde pero status no 200"

    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
        try:
            time.sleep(2.0)
            response = requests.get(url, timeout=10, proxies=no_proxy)
            if response.status_code == 200:
                data = response.json()
                procs = data.get("procesos", [])
                if procs:
                    return "activo", f"Activo ({', '.join(procs)}) [Retry]"
                else:
                    return "sin_proceso", "Sin procesos RPA corriendo [Retry]"
        except:
            if is_pingable(ip):
                return "sin_agente", "PC Encendida | Agente No Inició (Revisar .bat)"
            else:
                return "sin_agente", "Máquina Apagada o Sin Red (Ping Falló)"

    except Exception as e:
        return "sin_agente", f"Error Agente ({str(e)[:20]})"

    return "sin_agente", "Falla General"

def start_bot_via_agent(ip):
    try:
        url = f"http://{ip}:{config.AGENT_PORT}/start"
        res = requests.post(url, timeout=config.AGENT_TIMEOUT, proxies={"http": None, "https": None})
        return res.status_code == 200
    except:
        return False

def stop_bot_via_agent(ip):
    try:
        url = f"http://{ip}:{config.AGENT_PORT}/stop"
        res = requests.post(url, timeout=config.AGENT_TIMEOUT, proxies={"http": None, "https": None})
        return res.status_code == 200
    except:
        return False

def wait_bot_state(ip, desired_state, timeout_sec=90, poll_sec=3):
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        st, _ = check_process_via_agent(ip)
        if desired_state == "activo" and st == "activo":
            return True
        if desired_state == "no_activo" and st != "activo":
            return True
        time.sleep(poll_sec)
    return False

def extract_ips(text):
    if not text: return []
    # Aplanar texto para que IPs divididas por salto de linae se unan
    text = text.replace("\n", " ").replace("\r", " ")
    
    # 1. Búsqueda estándar (IPs perfectas)
    ips = re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text)
    
    # 2. Búsqueda tolerante para OCR (192.168 con espacios o puntos faltantes)
    # Detecta: "192.168 51.13", "192 168.1.1", "192.168.50 12"
    ocr_pattern = r"\b(192)[ .]?(168)[ .]?(\d{1,3})[ .]?(\d{1,3})\b"
    matches = re.findall(ocr_pattern, text)
    for m in matches:
        # Reconstruir como IP válida: "192.168.XX.YY"
        reconstructed = f"{m[0]}.{m[1]}.{m[2]}.{m[3]}"
        ips.append(reconstructed)

    clean = []
    for ip in ips:
        if ip == "0.0.0.0": continue
        parts = ip.split(".")
        try:
            if all(0 <= int(p) <= 255 for p in parts):
                clean.append(ip)
        except: pass
    
    # Eliminar duplicados manteniendo orden
    return list(dict.fromkeys(clean))

def matches_criteria(text):
    t = (text or "").lower()
    
    # 1. Busqueda literal
    if any(c in t for c in config.CRITERIOS):
        return True
        
    # 2. Busqueda por patrones (Regex es clave para 'no conectada', 'sin registro', etc.)
    for pattern in config.CRITERIOS_REGEX:
        if re.search(pattern, t):
            # print(f"    [DEBUG] Coincidencia Regex: '{pattern}' en '{t}'")
            return True
            
    return False

def remediate_ips(ips):
    for ip in ips:
        print(f"[VSCode] Analizando equipo... {ip}")
        print(f"[VSCode] Reiniciando bot (STOP/START) para IP: {ip}")

        ok_stop_cmd = stop_bot_via_agent(ip)
        if not ok_stop_cmd:
            print(f"[VSCode] Error: No se pudo enviar STOP a {ip}")
            continue

        ok_stop_state = wait_bot_state(ip, desired_state="no_activo", timeout_sec=90, poll_sec=3)
        if not ok_stop_state:
            print(f"[VSCode] Error: STOP no confirmado (timeout) en {ip}")

        print(f"[VSCode] PAUSA DE SEGURIDAD (60s) para verificar cierre de consolas en {ip}...")
        time.sleep(30)

        print(f"[VSCode] Ejecutando START para IP: {ip}")

        ok_start_cmd = start_bot_via_agent(ip)
        if not ok_start_cmd:
            print(f"[VSCode] Error: No se pudo enviar START a {ip}")
            continue

        ok_start_state = wait_bot_state(ip, desired_state="activo", timeout_sec=120, poll_sec=3)
        if ok_start_state:
            print(f"[VSCode] Reiniciando bot de equipo ({ip}) exitosamente")
        else:
            print(f"[VSCode] Error: START no confirmado (timeout) en {ip}")

# Variable global para evitar bucles de reinicio con el mismo mensaje
LAST_PROCESSED_TEXT = None
LAST_AUTOREPLY_TIME = 0

def check_and_handle_support_message(browser, page_proxmox):
    global LAST_PROCESSED_TEXT, LAST_AUTOREPLY_TIME
    # Ya no imprimimos spam, solo si hay mensaje
    # print("[VSCode] Revisando grupo de Teams (Soporte)...")

    msg = teams_bot.read_latest_message_from_group(browser, config.TEAMS_SUPPORT_GROUP_NAME, page_proxmox=page_proxmox)
    if not msg:
        return

    # Anti-rebote: Si el mensaje es idéntico al último procesado, ignorar.
    if msg == LAST_PROCESSED_TEXT:
        return

    print("[PAUSA] Mensaje nuevo detectado en Teams (soporte)")
    print(f"    [TEAMS LEIDO] Contenido Validado: \"{msg}\"")
    
    # Actualizar el último procesado
    LAST_PROCESSED_TEXT = msg

    msg_low = msg.lower()

    if not matches_criteria(msg_low):
        print("[VSCode] El analisis no corresponde con los criterios reanudando escaneo...")
        return

    ips = extract_ips(msg_low)
    # Asegurar unicidad total para evitar doble reinicio
    ips = list(set(ips))
    
    if not ips:
        print("[VSCode] El analisis coincide con criterios, pero no se detectaron IPs...")
        return

    print("[VSCode] Analizando... coincide con criterios")
    print(f"[VSCode] IPs a reiniciar: {', '.join(ips)}")

    # Notificación automática (Autoreply)
    try:
        import time
        import random
        
        if browser and hasattr(config, 'RESPUESTAS_SOPORTE'):
            frase = random.choice(config.RESPUESTAS_SOPORTE)

            # Espera segura
            print("[VSCode] Esperando 1 minuto antes de enviar autoreply...")
            time.sleep(60) 

            print(f"[VSCode] Enviando respuesta autoreply: '{frase}'...")
            teams_bot.send_teams_message(
                browser, 
                message=frase, 
                target_chat=config.TEAMS_SUPPORT_GROUP_NAME
            )

            print("[VSCode] Esperando 30s antes de proceder con el reinicio...")
            time.sleep(30) 
             
    except Exception as e:
        print(f"[VSCode] Nota: No se envió autoreply ({e})")

    remediate_ips(ips)
    print("[REANUDAR] Terminado soporte, retomando escaneo normal.\n")
