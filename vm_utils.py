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
    for intento in range(3):
        try:
            url = f"http://{ip}:{config.AGENT_PORT}/start"
            res = requests.post(url, timeout=config.AGENT_TIMEOUT, proxies={"http": None, "https": None})
            if res.status_code == 200:
                return True
        except Exception as e:
            if intento < 2: time.sleep(2)
            # print(f"    [DEBUG] Falló START intento {intento+1} en {ip}: {e}")
            pass
    return False

def stop_bot_via_agent(ip):
    for intento in range(3):
        try:
            url = f"http://{ip}:{config.AGENT_PORT}/stop"
            res = requests.post(url, timeout=config.AGENT_TIMEOUT, proxies={"http": None, "https": None})
            if res.status_code == 200:
                return True
        except Exception as e:
            if intento < 2: time.sleep(2)
            # print(f"    [DEBUG] Falló STOP intento {intento+1} en {ip}: {e}")
            pass
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
    
    return list(dict.fromkeys(clean))

def matches_criteria(text):
    t = (text or "").lower()
    if any(c in t for c in config.CRITERIOS):
        return True
    for pattern in config.CRITERIOS_REGEX:
        if re.search(pattern, t):
            return True
    return False

# >>> NUEVA FUNCION IZZI <<<
def activate_izzi_process(browser, target_ip):
    print(f"[IZZI LOGIC] Buscando IP {target_ip} en Dashboard...")
    try:
        page = None
        if browser.contexts:
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    if "frontrpaizzi" in pg.url:
                        page = pg
                        break
                if page: break
        
        if not page:
            print("    [IZZI ERROR] No se encontró la pestaña de Izzi.")
            return

        page.bring_to_front()
        time.sleep(1.0)

        # 1. Buscar fila (Usando Regex para evitar falsos positivos tipo .4 vs .40)
        # \bIP\b asegura coincidencia exacta
        try:
            row = page.locator("tr").filter(has_text=re.compile(rf"\b{re.escape(target_ip)}\b"))
        except:
            # Fallback simple si regex falla
            row = page.locator(f"tr:has-text('{target_ip}')")
        
        # Paginación simple (1 y 2)
        if row.count() == 0:
            print("    [IZZI] No encontrado en P1. Intentando P2...")
            btn2 = page.locator("ul.pagination li, button").filter(has_text="2").first
            if btn2.is_visible():
                btn2.click()
                time.sleep(2.0)
                try:
                    row = page.locator("tr").filter(has_text=re.compile(rf"\b{re.escape(target_ip)}\b"))
                except:
                    row = page.locator(f"tr:has-text('{target_ip}')")

        if row.count() > 0:
            print(f"    [IZZI] Fila encontrada para {target_ip}. Buscando controles...")
            
            # Asegurar que la fila sea visible (Scroll)
            row.first.scroll_into_view_if_needed()
            time.sleep(0.5)

            # 2. Click Dropdown (Estrategia PrimeNG <p-dropdown>)
            # Buscamos por tag p-dropdown que contenga el texto o placeholder
            dropdown = row.locator("p-dropdown").filter(has_text="Seleccione un comando").first
            
            # Si no lo encuentra por texto, intentamos por posición (el último p-dropdown de la fila)
            if dropdown.count() == 0:
                 dropdown = row.locator("p-dropdown").last
            
            if dropdown.is_visible():
                # Intentar dar clic en el disparador (flechita) o en el componente
                try:
                    trigger = dropdown.locator(".p-dropdown-trigger, .p-dropdown-label").first
                    if trigger.is_visible():
                        trigger.click(force=True)
                    else:
                        dropdown.click(force=True)
                        
                    time.sleep(1.0)
                    
                    # 3. Seleccionar "Iniciar Proceso" (Global en el body)
                    # En PrimeNG las opciones flotan en el body
                    opcion = page.locator("li, span, div").filter(has_text="Iniciar Proceso").last
                    
                    if opcion.is_visible():
                        opcion.click()
                        print(f"    [IZZI] Comando 'Iniciar Proceso' seleccionado. Esperando confirmación...")
                        time.sleep(1.0)
                        
                        # 4. Confirmación Final ("Si, Enviar") - Diálogo PrimeNG
                        # Esperamos a que la animación del dialogo termine y el botón exista
                        try:
                            # Intento 1: Por clase especifica (esperando hasta 3s)
                            btn_confirmar = page.locator("button.p-confirm-dialog-accept").first
                            btn_confirmar.wait_for(state="visible", timeout=3000)
                            btn_confirmar.click()
                            print(f"    [IZZI] Clic en maquina correctamente (Clase)")
    
                        except:
                            # Intento 2: Por Texto del Label (Estrategia infalible visual)
                            try:
                                print("    [IZZI] Buscando botón por texto...")
                                btn_label = page.locator("span.p-button-label").filter(has_text="Si, Enviar").first
                                btn_label.wait_for(state="visible", timeout=2000)
                                # Clic en el botón padre del span
                                btn_label.locator("..").click() 
                                print(f"    [IZZI] Clic en maquina correctamente (Texto)")
                            except Exception as e_btn:
                                print(f"    [IZZI ERROR] Botón 'Si, Enviar' no apareció ni por clase ni por texto. {e_btn}")
                        
                        time.sleep(2.0) # Esperar refresco post-clic
                        
                    else:
                        print("    [IZZI ERROR] Opción 'Iniciar Proceso' no apareció en la lista.")
                        
                except Exception as e_click:
                     print(f"    [IZZI CLICK ERROR] {e_click}")
            else:
                 print("    [IZZI ERROR] Dropdown PrimeNG no interactuable o no encontrado.")
        else:
            print(f"    [IZZI ERROR] IP {target_ip} no aparece en dashboard.")

    except Exception as e:
        print(f"    [IZZI EXCEPTION] {e}")

def remediate_ips(browser, ips):
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
        time.sleep(60)

        print(f"[VSCode] Ejecutando START para IP: {ip}")

        ok_start_cmd = start_bot_via_agent(ip)
        if not ok_start_cmd:
            print(f"[VSCode] Error: No se pudo enviar START a {ip}")
            continue

        ok_start_state = wait_bot_state(ip, desired_state="activo", timeout_sec=120, poll_sec=3)
        if ok_start_state:
            
            # >>> ACTIVAR EN IZZI <<<
            if browser:
                activate_izzi_process(browser, ip)
            
            print(f"[VSCode] Reiniciando bot de equipo ({ip}) exitosamente")
        else:
            print(f"[VSCode] Error: START no confirmado (timeout) en {ip}")

# Variable global para evitar bucles de reinicio con el mismo mensaje
LAST_PROCESSED_TEXT = None

def check_and_handle_support_message(browser, page_proxmox):
    global LAST_PROCESSED_TEXT
    
    msg = teams_bot.read_latest_message_from_group(browser, config.TEAMS_SUPPORT_GROUP_NAME, page_proxmox=page_proxmox)
    if not msg:
        return

    if msg == LAST_PROCESSED_TEXT:
        return

    print("[PAUSA] Mensaje nuevo detectado en Teams (soporte)")
    print(f"    [TEAMS LEIDO] Contenido Validado: \"{msg}\"")
    
    LAST_PROCESSED_TEXT = msg
    msg_low = msg.lower()

    if not matches_criteria(msg_low):
        print("[VSCode] El analisis no corresponde con los criterios reanudando escaneo...")
        return

    ips = extract_ips(msg_low)
    ips = list(set(ips))
    
    if not ips:
        print("[VSCode] El analisis coincide con criterios, pero no se detectaron IPs...")
        return

    print("[VSCode] Analizando... coincide con criterios")
    print(f"[VSCode] IPs a reiniciar: {', '.join(ips)}")

    # Autoreply
    try:
        if browser and hasattr(config, 'RESPUESTAS_SOPORTE'):
            frase = random.choice(config.RESPUESTAS_SOPORTE)

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

    # Pasar browser para interaccion Izzi
    remediate_ips(browser, ips)
    print("[REANUDAR] Terminado soporte, retomando escaneo normal.\n")
