from playwright.sync_api import sync_playwright
import time
import re
import cv2
import numpy as np
import os
import requests

DEBUG_PORT = 9222
AGENT_PORT = 5555
AGENT_TIMEOUT = 5

def check_ping(ip):
    if not ip or ip == "sin IP": return False
    try:
        param = '-n' if os.name == 'nt' else '-c'
        res = os.system(f"ping {param} 1 -w 1000 {ip} > nul 2>&1")
        return res == 0
    except:
        return False

def check_process_via_agent(ip):
    if not ip or ip == "sin IP": return "sin_agente", []
    try:
        url = f"http://{ip}:{AGENT_PORT}/status"
        response = requests.get(url, timeout=AGENT_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            return data.get("status", "desconocido"), data.get("procesos", [])
        return "error", []
    except:
        return "sin_agente", []

def start_bot_via_agent(ip):
    if not ip or ip == "sin IP": return False
    try:
        url = f"http://{ip}:{AGENT_PORT}/start"
        res = requests.post(url, timeout=AGENT_TIMEOUT)
        return res.status_code == 200
    except: return False

def check_process_visual(page):
    try:
        time.sleep(2.0)
        canvas = None
        if page.locator("canvas").count() > 0: 
            canvas = page.locator("canvas").first
        else:
            for frame in page.frames:
                if frame.locator("canvas").count() > 0:
                    canvas = frame.locator("canvas").first
                    break
            if not canvas: return "VNC no visible"
        if not canvas.is_visible(): return "VNC no visible"
        try: screenshot_bytes = canvas.screenshot(timeout=3000)
        except: screenshot_bytes = page.screenshot()
        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return "Error visual"
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        if w < 100 or h < 100: return "VNC no visible"
        roi_taskbar = gray[int(h*0.95):h, :]
        taskbar_mean = np.mean(roi_taskbar)
        roi_center = gray[int(h*0.2):int(h*0.8), int(w*0.2):int(w*0.8)]
        edges = cv2.Canny(roi_center, 50, 150)
        edge_density = np.sum(edges) / (roi_center.size) 
        if taskbar_mean < 20 and np.mean(gray) < 15: return "Maquina apagada"
        if edge_density > 8.0: return "Proceso activo"
        else: return "Proceso no activo"
    except:
        return "Error analisis"

# URL del canal de Teams
TEAMS_CHANNEL_URL = "https://teams.microsoft.com/l/channel/19%3A0113cb42e12f407fb933b4b1ac742dca%40thread.tacv2/logs_proxmox?groupId=9300d12e-bf09-4717-aefd-bc1a35d87fac&tenantId=caca42e2-ad4a-4d19-824c-3ff3709bd840"

def send_teams_message(browser, proxmox_page, message):
    """Envía mensaje a Teams cambiando de pestaña temporalmente."""
    try:
        # Buscar pestaña de Teams
        teams_page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "teams.microsoft.com" in pg.url:
                    teams_page = pg
                    break
            if teams_page: break
        
        if not teams_page:
            print("    [TEAMS] No se encontró Teams abierto")
            return False
        
        # Traer Teams al frente
        teams_page.bring_to_front()
        time.sleep(0.5)
        
        # Buscar el cuadro de texto y enviar mensaje
        input_box = teams_page.locator("div[contenteditable='true'], div[data-tid='ckeditor']").first
        if input_box.is_visible(timeout=3000):
            input_box.click(force=True)
            time.sleep(0.3)
            input_box.fill(message)
            time.sleep(0.3)
            teams_page.keyboard.press("Enter")
            time.sleep(0.5)
            
            # Volver a Proxmox
            proxmox_page.bring_to_front()
            return True
        else:
            proxmox_page.bring_to_front()
            return False
            
    except Exception as e:
        print(f"    [TEAMS] Error: {e}")
        try: proxmox_page.bring_to_front()
        except: pass
        return False


def check_teams_for_orders(browser, page_teams):
    """
    Fase 2: Revisa Teams (RPA izzi soporte II) por comandos de reinicio.
    """
    try:
        # Selector del chat
        chat_selector = page_teams.locator(".ui-tree-node, .ui-list-item").filter(has_text="RPA izzi soporte II")
        if chat_selector.count() == 0: return False

        # Verificar si hay indicador de no leido (negritas o badge)
        style = chat_selector.first.get_attribute("style") or ""
        cls = chat_selector.first.get_attribute("class") or ""
        badge = chat_selector.locator("[class*='badge'], [class*='unread']")
        
        is_unread = "bold" in style or "unread" in cls or (badge.count() > 0 and badge.first.is_visible())
        
        if not is_unread: return False

        # Si hay mensaje nuevo
        print("\n" + "!"*60)
        print("[ALERTA] Nuevo mensaje RPA izzi analizando...")
        print("!"*60 + "\n")
        
        # Click para leer (Traer al frente)
        page_teams.bring_to_front()
        chat_selector.first.click()
        time.sleep(3.0)
        
        # Leer ultimo mensaje
        last_msg = page_teams.locator("[data-tid='message-body'], .ui-chat__message-content").last
        if not last_msg.is_visible(): return False
        
        txt = last_msg.inner_text()
        print(f"[TEAMS] Mensaje: {txt[:100]}...")
        
        # Extraer IPs
        ips = re.findall(r'\b(?:192\.168\.(?:48|49|50|51|61)\.\d{1,3})\b', txt)
        ips = list(set(ips))
        
        if ips:
            print(f"[TEAMS] Orden para IPs: {ips}")
            for ip_t in ips:
                print(f"   -> Reiniciando {ip_t}...")
                if start_bot_via_agent(ip_t):
                    print("   -> Esperando 10s...")
                    time.sleep(10.0)
                    e, _ = check_process_via_agent(ip_t)
                    res = "Reiniciado OK" if e == "activo" else "No levanto"
                    print(f"   -> Resultado: {res}")
                else:
                    print(f"   -> Fallo envio comando a {ip_t}")
        else:
            print("[TEAMS] No se detectaron IPs validas.")
            
        print("[INFO] Regresando a vigilancia...\n")
        return True
        
    except Exception as e:
        print(f"[ERROR TEAMS] {e}")
        return False
        
def main():
    print("Conectando a Chrome...\n")
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    except: 
        print("[ERROR] No se pudo conectar")
        return

    page = None
    page_teams = None # Variable nueva Phase 2

    for ctx in browser.contexts:
        for pg in ctx.pages:
            url = pg.url.lower()
            # Proxmox estricto (:8006)
            if ":8006" in url:
                page = pg
            # Teams estricto
            elif "teams.microsoft.com" in url:
                page_teams = pg
    
    if not page:
        # Fallback anterior
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "proxmox" in pg.url and "teams" not in pg.url:
                    page = pg; break
    
    if not page:
        print("[ERROR] No se encontró Proxmox.")
        return

    if page_teams:
        print("[INFO] Teams detectado. Modo Escucha ON.")
    else:
        print("[WARN] Teams no detectado. Solo escaneo.")

    print("=" * 60)
    print(" AGENTE PROXMOX - MODO VIGILANCIA CONTINUA")
    print("=" * 60 + "\n")

    while True:  # BUCLE INFINITO [PRODUCCION]
        timestamp = time.strftime("%Y-%m-%d") # Solo FECHA
        print(f"\n[{timestamp}] INICIANDO CICLO DE ESCANEO...")
        
        manual_scan_done = False  # Resetear bandera para este ciclo
        
        # 0. RESET DE NAVEGACIÓN (Volver arriba para evitar desfaces)
        try:
            page.bring_to_front() # Asegurar Foco Proxmox
            page.locator("body").click(force=True)
            page.keyboard.press("Home")
            time.sleep(1.0)
        except: pass

        row_selector = ".x-grid-item, .x-grid-row"
        try:
            page.wait_for_selector(row_selector, timeout=10000)
        except: 
            print("[ERROR] Timeout esperando lista")
            time.sleep(60)
            continue

        rows = page.locator(row_selector)
        start_index = 0
        for i in range(rows.count()):
            txt = rows.nth(i).inner_text().strip()
            if re.match(r"^\d+.*", txt):
                start_index = i
                break

        print(f"{'VIX':<24} | {'IP':<15} | PROCESO")
        print("-" * 60)

        seen_vmids = set()
        total_rows = page.locator(row_selector).count()

        for i in range(start_index, total_rows):
            
            # --- HOOK FASE 2: Checar Teams antes de cada VM ---
            if page_teams:
                if check_teams_for_orders(browser, page_teams):
                    # Si atendio algo, aseguramos foco de vuelta en Proxmox
                    try: page.bring_to_front(); time.sleep(1.0)
                    except: pass
            # --------------------------------------------------

            try:
                current_row = page.locator(row_selector).nth(i)
                current_row.scroll_into_view_if_needed()
                time.sleep(0.3)
                txt = current_row.inner_text().strip()
                if not re.match(r"^\d+.*", txt):
                    continue
                current_row.click(force=True, timeout=3000)
                time.sleep(1.0)
            except:
                continue

            vmid, name = "unknown", "unknown"
            try:
                header = page.locator(".x-title-text, .x-panel-header-text, div").filter(
                    has_text=re.compile(r"Virtual Machine \d+")
                ).first
                if header.is_visible():
                    m = re.search(r"Virtual Machine (\d+)\s*\((.+)\)", header.inner_text())
                    if m:
                        vmid, name = m.group(1), m.group(2)
            except:
                pass

            if vmid == "unknown" or vmid in seen_vmids:
                continue

            # =====================================================================
            # ESCANEO MANUAL (Solo VMs 152-161 que se saltan)
            # =====================================================================
            # Se activa si vemos cualquier VM dentro o después del hueco (>= 152)
            # MOVIDO AQUI: Para que se ejecute ANTES de imprimir la VM actual (ej: 165), manteniendo el orden visual.
            if vmid.isdigit() and int(vmid) >= 152 and not manual_scan_done:
                print("\n    [INFO] Ejecutando Escaneo Manual (VMs 152-161)...")
                # send_teams_message(browser, page, "[INFO] Escaneando VMs 152-161 manualmente...")
                
                manual_scan_done = True 

                # Solo las 152-161
                vms_manuales = {
                    "152 vix39": "192.168.49.83",
                    "153 vix40": "192.168.49.84",
                    "154 vix41": "192.168.49.86",
                    "155 vix42": "192.168.49.87",
                    "156 vix43": "192.168.51.88",
                    "157 vix44": "192.168.51.89",
                    "158 vix45": "192.168.51.90",
                    "159 vix46": "192.168.51.91",
                    "160 47RAM": "192.168.48.91",
                    "161 AzRpa": "192.168.48.224",
                }
                
                for vm_name, ip_vm in vms_manuales.items():
                    print(f"    [INFO] Consultando {vm_name} en {ip_vm}...")
                    e, p = check_process_via_agent(ip_vm)
                    
                    if e == "activo":
                        resultado = f"Activo ({','.join(p)})"
                    elif e == "sin_proceso":
                        resultado = "INICIADO" if start_bot_via_agent(ip_vm) else "Fallo"
                    else:
                        ping = "OK" if check_ping(ip_vm) else "FAIL"
                        resultado = f"Sin Agente - Ping: {ping}"
                    
                    msg_manual = f"{vm_name:<24} | {ip_vm:<15} | {resultado}"
                    print(msg_manual)
                    
                    # FILTRO MANUAL
                    notify_m = True
                    if resultado.startswith("Activo ("): notify_m = False
                    if "192.168.49.76" in ip_vm: notify_m = False
                    
                    if notify_m:
                         # send_teams_message(browser, page, msg_manual)
                         pass
                
                print("    [INFO] Fin escaneo manual.\n")

            seen_vmids.add(vmid)
            display_name = f"{vmid} {name}"

            # IP
            ip = "sin IP"
            try:
                summary_btn = page.locator(".x-treelist-item, .x-grid-cell-inner", 
                    has_text=re.compile(r"Summary|Resumen", re.I)).first
                if summary_btn.is_visible():
                    summary_btn.click(force=True)
                    time.sleep(1.0)
                notes = page.locator('[id*="pveNotesView"]').first
                if notes.is_visible():
                    m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', notes.inner_text())
                    if m: ip = m.group(1)
            except:
                pass

            # Consola
            try:
                console = page.locator(".x-treelist-item-text").filter(
                    has_text=re.compile(r"Console|Consola", re.I)).last
                if console.is_visible():
                    print("    [INFO] Clic en >_ Console...")
                    console.click(force=True)
                    time.sleep(5.0)
            except:
                pass

            # Agente
            print(f"    [INFO] Consultando Agente en {ip}...")
            estado, procs = check_process_via_agent(ip)
            
            if estado != "sin_agente" and estado != "error":
                if estado == "activo":
                    resultado = f"Activo ({', '.join(procs)})"
                else:
                    print("    [INFO] INACTIVO. Enviando START...")
                    resultado = "INICIADO" if start_bot_via_agent(ip) else "Fallo al iniciar"
            else:
                ping = "OK" if check_ping(ip) else "FAIL"
                print(f"    [WARN] Sin Agente (Ping: {ping}). Analizando...")
                visual = check_process_visual(page)
                resultado = f"{visual} (Sin Agente) - Ping: {ping}"

            log_msg = f"{display_name:<24} | {ip:<15} | {resultado}"
            print(log_msg)
            
            # === FILTROS DE NOTIFICACIÓN A TEAMS ===
            notify = True

            # 1. CRITERIOS DE SALUD (Si cumple, NO molestar)
            # - Si el Agente dice "Activo"
            # - O si el Visual dice "Proceso activo" (para casos donde falla la red/Ping pero el bot se ve corriendo)
            if resultado.startswith("Activo (") or resultado.startswith("Proceso activo"):
                notify = False

            # 2. EXCEPCIONES ESPECÍFICAS (IPs o Nombres prohibidos en Teams)
            if "192.168.49.76" in ip: notify = False
            if "vix18" in name.lower() or "130" in vmid: notify = False
                
            if notify:
                # send_teams_message(browser, page, log_msg)
                pass

            # VIX18
            if "130" in vmid or "vix18" in name.lower():
                print("\n    [INFO] VIX18 - Escaneando hijas...")
                # NOTA: Comentamos el envío global de VIX18 a Teams para no saturar
                # send_teams_message(browser, page, "[INFO] VIX18 - Escaneando hijas...")
                
                ips_hijas = [
                    "192.168.49.76", "192.168.61.30", "192.168.61.50", "192.168.61.51", 
                    "192.168.61.31", "192.168.61.18", "192.168.61.43", "192.168.61.44", 
                    "192.168.61.45", "192.168.61.28", "192.168.61.42", "192.168.61.23", 
                    "192.168.61.5", "192.168.61.4", "192.168.51.204", "192.168.51.203", 
                    "192.168.51.202", "192.168.51.201", "192.168.51.195", "192.168.51.194", 
                    "192.168.51.193", "192.168.51.192", "192.168.51.191", "192.168.51.190", 
                    "192.168.51.189"
                ]
                for ip_h in ips_hijas:
                    print(f"    [INFO] Consultando hija en {ip_h}...")
                    e, p = check_process_via_agent(ip_h)
                    
                    if e == "activo":
                        resultado = f"Activo ({','.join(p)})"
                    elif e == "sin_proceso":
                        print(f"    [INFO] Hija {ip_h} INACTIVA. Enviando START...")
                        resultado = "INICIADO" if start_bot_via_agent(ip_h) else "Fallo al iniciar"
                    else:
                        ping = "OK" if check_ping(ip_h) else "FAIL"
                        resultado = f"Sin Agente - Ping: {ping}"
                    
                    msg_hija = f"   -> [HIJA VIX18] {ip_h:<15} | {resultado}"
                    print(msg_hija)
                    
                    # FILTRO VIX18: NO MANDAR NADA A TEAMS (SOLICITADO POR USUARIO)
                    # if not resultado.startswith("Activo (") and "192.168.49.76" not in ip_h:
                    #    send_teams_message(browser, page, msg_hija)
                print()



        print("\n" + "=" * 60)
        print(f"  CICLO COMPLETADO ({len(seen_vmids)} VMs escaneadas)")
        print("=" * 60)
        
        print("\n[ESPERA] Durmiendo 20 minutos antes del próximo ciclo...")
        time.sleep(1200)  # 20 minutos

if __name__ == "__main__":
    main()