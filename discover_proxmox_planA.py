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

def check_process_via_agent(ip):
    """
    Consulta el agente en la VM para obtener estado del proceso.
    Retorna: ("activo", ["python.exe"]) o ("sin_proceso", []) o ("sin_agente", [])
    """
    if not ip or ip == "sin IP":
        return "sin_agente", []
    
    try:
        url = f"http://{ip}:{AGENT_PORT}/status"
        response = requests.get(url, timeout=AGENT_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            status = data.get("status", "desconocido")
            procesos = data.get("procesos", [])
            return status, procesos
        else:
            return "error", []
            
    except requests.exceptions.Timeout:
        return "sin_agente", []
    except requests.exceptions.ConnectionError:
        return "sin_agente", []
    except Exception as e:
        return "error", []

def start_bot_via_agent(ip):
    """
    Envia comando al agente para iniciar el bot.
    """
    if not ip or ip == "sin IP":
        return False
    
    try:
        url = f"http://{ip}:{AGENT_PORT}/start"
        response = requests.post(url, timeout=AGENT_TIMEOUT)
        return response.status_code == 200
    except:
        return False

def check_process_visual(page):
    """
    Analiza visualmente el estado de la VM.
    Busca el canvas en todos los frames (posible iframe).
    """
    try:
        # Dar tiempo para render
        time.sleep(2.0)
        
        # Buscar el frame que contiene el VNC
        vnc_frame = None
        # Primero buscamos en la pagina principal
        if page.locator("canvas").count() > 0:
            canvas = page.locator("canvas").first
        else:
            # Buscar en iframes
            found = False
            for frame in page.frames:
                if frame.locator("canvas").count() > 0:
                    canvas = frame.locator("canvas").first
                    found = True
                    break
            if not found:
                print("    [WARN] No se encontró elemento <canvas> en ningún frame")
                return "VNC no visible"

        if not canvas.is_visible():
            print("    [WARN] Canvas encontrado pero no visible")
            return "VNC no visible"

        # Capturar pantalla del canvas
        # NOTA: A veces capturar el canvas directo falla si es WebGL acelerado.
        # Fallback: Capturar la pagina/frame completo si el canvas falla.
        try:
            screenshot_bytes = canvas.screenshot(timeout=3000)
        except:
            print("    [INFO] Screenshot de canvas falló, intentando pantalla completa...")
            screenshot_bytes = page.screenshot()

        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return "Error visual"

        # Guardar la imagen exacta que está analizando el robot
        cv2.imwrite("debug_analisis_actual.png", img)
        
        # --- ANÁLISIS ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Si la imagen es muy pequeña (ej error de carga), descartar
        if w < 100 or h < 100:
            return "VNC no visible"

        # 1. Región BARRA DE TAREAS (Fondo del todo)
        roi_taskbar = gray[int(h*0.95):h, :]
        taskbar_mean = np.mean(roi_taskbar)
        
        # Pantalla negra / Conectando... (a veces es gris oscuro)
        if taskbar_mean < 20:
             # Chequear si es todo negro (apagado)
             if np.mean(gray) < 15:
                 return "Maquina apagada"
             else:
                 # Podria ser pantalla de carga "Proxmox" negra con logo
                 return "Maquina apagada" 

        # 2. Región CENTRAL (Escritorio vs Ventanas)
        roi_center = gray[int(h*0.2):int(h*0.8), int(w*0.2):int(w*0.8)]
        edges = cv2.Canny(roi_center, 50, 150)
        edge_density = np.sum(edges) / (roi_center.size) 
        
        # Si hay muchos bordes -> Ventanas abiertas
        if edge_density > 8.0: 
            return "Proceso activo"
        else:
            return "Proceso no activo"

    except Exception as e:
        print(f"[WARN] Error analisis visual: {e}")
        return "Error analisis"

def find_teams_page(browser):
    """Busca la pestaña de Teams en el contexto del navegador."""
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "teams.microsoft.com" in pg.url:
                return pg
    return None

def send_teams_message(teams_page, message):
    """Envía un mensaje al chat activo de Teams."""
    if not teams_page:
        return
    try:
        # Selector genérico para el input de mensaje en Teams (V2)
        # Busca un div editable o con role textbox
        input_box = teams_page.locator("div[contenteditable='true'], div[role='textbox']").first
        if input_box.is_visible():
            input_box.fill(message)
            input_box.press("Enter")
            time.sleep(0.5)
    except Exception as e:
        print(f"[WARN] No se pudo enviar a Teams: {e}")

def main():
    print("Conectando a Chrome...\n")
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    except Exception as e:
        print(f"[ERROR] Conexión fallida: {e}")
        return

    # Buscar pestaña de Proxmox
    page = None
    teams_page = None # Variable para la pestaña de Teams
    
    # Buscar pestañas
    teams_page = find_teams_page(browser)
    if teams_page:
        print("[INFO] Conectando con Teams")
    else:
        print("[WARN] No se encontró pestaña de Teams. Los reportes solo saldrán en consola.")

    for ctx in browser.contexts:
        for pg in ctx.pages:
            url = pg.url.lower()
            if "proxmox" in url or "192.168" in url or ":8006" in url or "10." in url:
                page = pg
                break
        if page:
            break

    if not page:
        print("[ERROR] No se encontró Proxmox.")
        return

    try:
        page.bring_to_front()
    except:
        pass

    print("=" * 60)
    print(" AGENTE PROXMOX")
    print("=" * 60 + "\n")

    row_selector = ".x-grid-item, .x-grid-row"
    try:
        page.wait_for_selector(row_selector, timeout=5000)
    except:
        print("[ERROR] No se detectan máquinas.")
        return

    rows = page.locator(row_selector)
    start_index = -1
    for i in range(rows.count()):
        txt = rows.nth(i).inner_text().strip()
        if re.match(r"^\d+.*", txt):
            start_index = i
            break

    if start_index == -1:
        print("[ERROR] No se encontró ninguna VM.")
        return

    header_msg = f"{'VIX':<24} | {'IP':<15} | PROCESO"
    print(header_msg)
    print("-" * 60)
    
    # Enviar cabecera a Teams si existe
    if teams_page:
        send_teams_message(teams_page, "Iniciando escaneo de Proxmox...")

    seen_vmids = set()
    total_rows = page.locator(row_selector).count()

    for i in range(start_index, total_rows):
        try:
            current_row = page.locator(row_selector).nth(i)
            current_row.scroll_into_view_if_needed()
            time.sleep(0.2)

            txt = current_row.inner_text().strip()
            if not re.match(r"^\d+.*", txt):
                continue

            current_row.click(force=True, timeout=3000)
            time.sleep(1.0)
        except:
            page.keyboard.press("ArrowDown")
            time.sleep(0.5)
            continue

        # Identificar VM
        vmid, name = "unknown", "unknown"
        try:
            header = page.locator(".x-title-text, .x-panel-header-text, div").filter(
                has_text=re.compile(r"Virtual Machine \d+")
            ).first
            if header.is_visible():
                header_text = header.inner_text()
                m = re.search(r"Virtual Machine (\d+)\s*\((.+)\)", header_text)
                if m:
                    vmid, name = m.group(1), m.group(2)
        except:
            pass

        if vmid == "unknown" or vmid in seen_vmids:
            continue

        seen_vmids.add(vmid)
        display_name = f"{vmid} {name}"

        # Leer IP (Summary)
        ip = "sin IP"
        try:
            summary_btn = page.locator(".x-treelist-item, .x-grid-cell-inner", 
                has_text=re.compile(r"Summary|Resumen", re.I)).first
            if summary_btn.is_visible():
                summary_btn.click(force=True)
                time.sleep(1.5)

            notes = page.locator('[id*="pveNotesView"]').first
            if notes.is_visible():
                m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', notes.inner_text())
                if m:
                    ip = m.group(1)
        except:
            pass

        # Dar clic en Console (como estaba antes)
        # Dar clic en Console
        try:
            # Selector OFICIAL de Proxmox para el item del arbol lateral
            console_menu_item = page.locator(".x-treelist-item-text").filter(has_text=re.compile(r"Console|Consola", re.I)).last
            
            if console_menu_item.is_visible():
                print("    [INFO] Clic en >_ Console...")
                console_menu_item.click(force=True)
                
                # Esperar explicitamente al panel de noVNC o xterm
                print(f"    [INFO] Esperando carga de VNC (10s)...")
                time.sleep(10.0)
            else:
                print("    [WARN] Botón Console no visible")
        except Exception as e:
            print(f"    [ERROR] Falló clic en Console: {e}")

        # ANÁLISIS VISUAL (Prioritario según solicitud)
        proceso = check_process_visual(page)
        
        # Si visualmente no hay proceso, intentamos iniciar con el agente (si existe)
        if proceso == "Proceso no activo":
            # Intentar iniciar
            started = start_bot_via_agent(ip)
            if started:
                proceso = "Proceso no activo (Iniciando...)"
        
        # Fallback: Si el visual falló, consultamos agente
        if proceso in ["Error visual", "VNC no visible"]:
            estado_ag, procs_ag = check_process_via_agent(ip)
            if estado_ag == "activo":
                proceso = f"Activo (Agente: {', '.join(procs_ag)})"
            elif estado_ag == "sin_agente":
                proceso = "Error visual (Sin agente)"

        log_msg = f"{display_name:<24} | {ip:<15} | {proceso}"
        print(log_msg)
        
        # Enviar log a Teams si existe
        if teams_page:
            send_teams_message(teams_page, log_msg)

    print("\n" + "=" * 60)
    print("  RECORRIDO COMPLETADO")
    print("=" * 60)
    p.stop()

if __name__ == "__main__":
    main()