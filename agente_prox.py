from playwright.sync_api import sync_playwright
import time
import requests
import re
import sys
import subprocess
import platform

# >>> NUEVO (OCR LOCAL) <<<
import pytesseract
import cv2
from PIL import Image

# Configuración
DEBUG_PORT = 9222
AGENT_PORT = 5555
AGENT_TIMEOUT = 5

# URL del canal logs_proxmox (Referencia)
TEAMS_CHANNEL_URL = "https://teams.microsoft.com/l/channel/19%3A0113cb42e12f407fb933b4b1ac742dca%40thread.tacv2/logs_proxmox?groupId=9300d12e-bf09-4717-aefd-bc1a35d87fac&tenantId=caca42e2-ad4a-4d19-824c-3ff3709bd840"

# >>> NUEVO: nombre exacto del chat de soporte <<<
TEAMS_SUPPORT_GROUP_NAME = "RPA izzi soporte II"

# >>> NUEVO: criterios operativos <<<
CRITERIOS = [
    "no conectado",
    "no conectados",
    "sin registros",
    "no ha tomado registros",
    "no tomo registros",
    "bot detenido",
    "sin conexión",
    "no responde",
    "sin tomar registros",
]

# >>> NUEVO: dedupe para no procesar el mismo mensaje 2 veces <<<
LAST_TEAMS_HASH = None


def is_pingable(ip):
    """Verifica si la máquina responde a Ping (ICMP)."""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    cmd = ['ping', param, '1', ip]
    try:
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except:
        return False


def check_process_via_agent(ip):
    """Consulta directa al agente con Diagnóstico Avanzado (Ping vs Puerto)."""
    url = f"http://{ip}:{AGENT_PORT}/status"
    no_proxy = {"http": None, "https": None}

    try:
        response = requests.get(url, timeout=AGENT_TIMEOUT, proxies=no_proxy)
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
    """Envía orden de START al Agente."""
    try:
        url = f"http://{ip}:{AGENT_PORT}/start"
        res = requests.post(url, timeout=AGENT_TIMEOUT, proxies={"http": None, "https": None})
        return res.status_code == 200
    except:
        return False


# >>> NUEVO: STOP por agente (ya existe en tu agente actualizado) <<<
def stop_bot_via_agent(ip):
    try:
        url = f"http://{ip}:{AGENT_PORT}/stop"
        res = requests.post(url, timeout=AGENT_TIMEOUT, proxies={"http": None, "https": None})
        return res.status_code == 200
    except:
        return False


# >>> NUEVO: confirmación real del estado <<<
def wait_bot_state(ip, desired_state, timeout_sec=90, poll_sec=3):
    """
    desired_state:
      - 'activo'    => espera status == 'activo'
      - 'no_activo' => espera status != 'activo'
    """
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        st, _ = check_process_via_agent(ip)
        if desired_state == "activo" and st == "activo":
            return True
        if desired_state == "no_activo" and st != "activo":
            return True
        time.sleep(poll_sec)
    return False


# >>> NUEVO: Cache alertas diarias <<<
ALERTS_SENT_CACHE = set()

def send_teams_message(browser, message, target_chat="logs_proxmox"):
    """Busca la pestaña de Teams, cambia al chat objetivo y envia mensaje."""
    try:
        page_teams = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "teams.microsoft.com" in pg.url:
                    page_teams = pg
                    break
            if page_teams:
                break

        if not page_teams:
            print("    [TEAMS ERROR] No se encontró pestaña de Teams abierta.")
            return False 

        print(f"    [TEAMS] Enviando alerta para: {message.split('|')[0]}...")
        page_teams.bring_to_front()
        time.sleep(0.5)

        # REGLA 2: Asegurar canal correcto
        if target_chat:
            chat_item = teams_find_chat_item(page_teams, target_chat)
            if chat_item:
                chat_item.click(force=True)
                time.sleep(1.0) # Esperar carga del chat
            else:
                # Fallback URL si no encuentra visualmente
                if target_chat == "logs_proxmox" and TEAMS_CHANNEL_URL:
                     print("    [TEAMS] Chat no visible, intentando navegación URL...")
                     page_teams.goto(TEAMS_CHANNEL_URL)
                     time.sleep(3.0)
        
        input_box = page_teams.locator("div[contenteditable='true'], div[data-tid='ckeditor']").first
        if input_box.is_visible(timeout=5000):
            input_box.click(force=True)
            input_box.fill(message)
            page_teams.keyboard.press("Enter")
            time.sleep(0.5)
            return True
        else:
            print("    [TEAMS ERROR] No se encontró cuadro de texto (Chat no seleccionado).")
            return False
    except Exception as e:
        print(f"    [TEAMS EXCEPTION] {e}")
        return False
        return False


# =========================
# >>> NUEVO: TEAMS + OCR + SOPORTE ON-DEMAND
# =========================

def get_teams_page(browser):
    try:
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "teams.microsoft.com" in pg.url:
                    return pg
    except:
        pass
    return None


def ocr_image(path):
    try:
        img = cv2.imread(path)
        if img is None:
            return ""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)[1]
        tmp = "ocr_tmp.png"
        cv2.imwrite(tmp, gray)
        txt = pytesseract.image_to_string(Image.open(tmp), lang="spa")
        return (txt or "").strip()
    except:
        return ""


def extract_ips(text):
    if not text:
        return []
    ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    clean = []
    for ip in ips:
        if ip == "0.0.0.0":
            continue
        parts = ip.split(".")
        try:
            if all(0 <= int(p) <= 255 for p in parts):
                clean.append(ip)
        except:
            pass
    return list(dict.fromkeys(clean))


def matches_criteria(text):
    t = (text or "").lower()
    return any(c in t for c in CRITERIOS)


def teams_find_chat_item(page, name):
    """
    Selector tolerante para Teams v2: busca el item por texto visible.
    """
    # Lista de chats suele ser un árbol; esto suele funcionar mejor que title exacto.
    # Usamos regex ignorando mayúsculas/minúsculas para mayor robustez
    import re
    pattern = re.compile(re.escape(name), re.IGNORECASE)
    
    candidates = [
        page.locator("div[role='treeitem']").filter(has_text=pattern).first,
        page.locator("li").filter(has_text=pattern).first,
        page.locator("span").filter(has_text=pattern).first,
    ]
    for loc in candidates:
        try:
            # Modificación: No requerimos visibilidad inmediata (timeout),
            # confiamos en que al intentar clickear después, Playwright hará scroll.
            if loc.count() > 0:
                return loc
        except:
            pass
    return None


# >>> NUEVO: (Se deja intacta aunque ya no sea requerida) <<<
def teams_group_has_new_message(browser, group_name):
    page = get_teams_page(browser)
    if not page:
        return False
    try:
        item = teams_find_chat_item(page, group_name)
        if not item:
            return False
        badge = item.locator(
            "span[aria-label*='mensaje'], span[aria-label*='Mensajes'], span[data-tid*='unread'], i[data-tid*='unread']"
        )
        return badge.count() > 0
    except:
        return False


# >>> MOD MÍNIMA: solo agrego wait_for_selector para estabilidad, resto igual <<<
def read_latest_message_from_group(browser, group_name, page_proxmox=None):
    """Lee el último mensaje usando Navegación Clásica + Scraping Robusto."""
    global LAST_TEAMS_HASH
    page = get_teams_page(browser)
    if not page:
        print("[TEAMS ERROR] No hay pagina Teams.")
        return None

    try:
        page.bring_to_front()
        time.sleep(0.3)

        # 1. NAVEGACIÓN CLÁSICA (Que sí funcionaba)
        item = teams_find_chat_item(page, group_name)
        if not item:
            print(f"    [TEAMS ERROR] No encontré el chat '{group_name}' en la lista lateral.")
            return None
        
        item.click(force=True)
        time.sleep(1.5) # Espera carga mensajes

        # 2. EXTRACCIÓN CON SELECTORES ACTUALIZADOS (Usuario)
        txt = None
        try:
            # Selectores constantes
            SEL_MESSAGE = 'div[data-tid="chat-pane-message"]'
            SEL_TEXT    = 'div[data-message-content] p'
            SEL_IMAGE   = 'img[data-tid^="lazy-image"]'

            # Esperamos a que aparezcan mensajes
            try:
                page.wait_for_selector(SEL_MESSAGE, timeout=5000)
            except:
                print("    [TEAMS ERROR] Timeout: No se detectaron mensajes (selector nuevo).")
                return None

            # Obtenemos el contenedor del ÚLTIMO mensaje
            last_container = page.locator(SEL_MESSAGE).last
            
            parts = []

            # A) Intentamos leer TEXTO (Párrafo interno)
            txt_locator = last_container.locator(SEL_TEXT)
            if txt_locator.count() > 0:
                text_content = " ".join(txt_locator.all_inner_texts())
                if text_content.strip():
                    parts.append(text_content.strip())
            
            # B) SIEMPRE buscamos IMAGEN (OCR) para complementar
            img_locator = last_container.locator(SEL_IMAGE)
            if img_locator.count() > 0:
                # print("    [TEAMS] Imagen detectada, escaneando contenido...")
                img_path = "teams_latest.png"
                try:
                    img_locator.last.screenshot(path=img_path)
                    ocr_res = ocr_image(img_path)
                    if ocr_res and ocr_res.strip():
                        parts.append(f"[OCR: {ocr_res.strip()}]")
                except:
                    pass

            txt = " ".join(parts)
            
            if not txt:
                 # Fallback ultimo recurso: texto bruto del contenedor mensaje
                 txt = last_container.inner_text()

        except Exception as e:
            print(f"    [TEAMS ERROR] Extracción falló: {e}")
            return None

        if not txt:
            return None

        txt_norm = txt.strip()
        h = hash(txt_norm)
        
        # LOG VISIBLE
        state_label = "REPETIDO" if LAST_TEAMS_HASH == h else "NUEVO"
        if state_label == "NUEVO":
            print(f"    [TEAMS EXTRACT] {state_label}: \"{txt_norm[:80]}...\"")

        if LAST_TEAMS_HASH == h:
            return None
        LAST_TEAMS_HASH = h

        # Volver a Proxmox
        try:
            if page_proxmox:
                page_proxmox.bring_to_front()
                time.sleep(0.2)
        except:
            pass

        return txt_norm
    except:
        try:
            if page_proxmox:
                page_proxmox.bring_to_front()
        except:
            pass
        return None


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


# >>> CAMBIO MÍNIMO: YA NO DEPENDE DE BADGE. Solo esto. <<<
def check_and_handle_support_message(browser, page_proxmox):
    print("[VSCode] Revisando grupo de Teams (RPA izzi soporte II)...")

    # Ya no dependemos del badge, leemos y el dedupe decide si es nuevo
    msg = read_latest_message_from_group(browser, TEAMS_SUPPORT_GROUP_NAME, page_proxmox=page_proxmox)
    if not msg:
        return

    print("[PAUSA] Mensaje nuevo detectado en Teams (soporte)")

    print(f"    [TEAMS LEIDO] Contenido Validado: \"{msg}\"")

    msg_low = msg.lower()

    if not matches_criteria(msg_low):
        print("[VSCode] El analisis no corresponde con los criterios reanudando escaneo...")
        return

    ips = extract_ips(msg_low)
    if not ips:
        print("[VSCode] El analisis coincide con criterios, pero no se detectaron IPs...")
        return

    print("[VSCode] Analizando... coincide con criterios")
    print(f"[VSCode] IPs a reiniciar: {', '.join(ips)}")

    remediate_ips(ips)
    print("[REANUDAR] Terminado soporte, retomando escaneo normal.\n")


def main():
    print("=" * 60)
    print(" AGENTE PROXMOX - MODO VIGILANCIA RPA")
    print("=" * 60 + "\n")

    with sync_playwright() as p:
        while True:  # BUCLE INFINITO
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            msg_inicio = f"[{timestamp}] INICIANDO CICLO DE ESCANEO..."
            print(msg_inicio)
            print(f"{'VIX':<24} | {'IP':<15} | PROCESO")
            print("-" * 60)

            try:
                browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
                context = browser.contexts[0]
                page = None
                for pg in context.pages:
                    if ":8006" in pg.url.lower():
                        page = pg
                        break

                send_teams_message(browser, msg_inicio)

                if not page:
                    print("[ERROR] No se encontró pestaña Proxmox (:8006).")

                try:
                    page.evaluate(
                        "Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: true}); "
                        "document.dispatchEvent(new Event('visibilitychange'));"
                    )
                except:
                    pass
                try:
                    page.bring_to_front()
                    time.sleep(0.5)
                except:
                    pass

            except Exception as e:
                print(f"[ERROR] Conexión Navegador: {e}")
                page = None
                browser = None

            # 3. LISTA DE MAQUINAS PRINCIPALES
            lista_vms = [
                ("110", "192.168.49.109"),
                ("120", "192.168.49.76"),
                ("121", "192.168.49.151"),
                ("123", "192.168.49.21"),
                ("124", "192.168.49.22"),
                ("125", "192.168.51.164"),
                ("126", "192.168.49.31"),
                ("127", "192.168.49.25"),
                ("128", "192.168.49.26"),
                ("129", "192.168.49.127"),
                ("130", "192.168.49.28"),
                ("131", "192.168.49.29"),
                ("132", "192.168.49.30"),
                ("133", "192.168.49.33"),
                ("134", "192.168.51.13"),
                ("135", "192.168.51.48"),
                ("136", "192.168.51.183"),
                ("137", "192.168.49.36"),
                ("138", "192.168.49.37"),
                ("139", "192.168.49.57"),
                ("140", "192.168.49.58"),
                ("141", "192.168.49.40"),
                ("142", "192.168.50.49"),
                ("143", "192.168.51.14"),
                ("144", "192.168.49.43"),
                ("145", "192.168.49.90"),
                ("165", "192.168.48.225"),
                ("167", "192.168.51.16"),
                ("168", "192.168.51.17"),
                ("169", "192.168.51.20"),
                ("170", "192.168.51.28"),
                ("171", "192.168.51.30"),
                ("172", "192.168.51.44"),
                ("111", "0.0.0.0"),
                ("146", "192.168.49.77"),
                ("147", "192.168.49.78"),
                ("148", "192.168.49.79"),
                ("149", "192.168.49.80"),
                ("150", "192.168.49.81"),
                ("151", "192.168.49.82"),
                ("152", "192.168.49.83"),
                ("153", "192.168.49.84"),
                ("154", "192.168.49.86"),
                ("155", "192.168.49.87"),
                ("156", "192.168.51.88"),
                ("157", "192.168.51.89"),
                ("158", "192.168.51.90"),
                ("159", "192.168.51.91"),
                ("160", "192.168.48.91"),
                ("161", "192.168.48.224"),
                ("162", "192.168.51.57"),
                ("163", "192.168.50.37"),
                ("164", "192.168.48.225"),
                ("110 (Equipo19)", "192.168.49.94"), # nuevas maquinas agregadas
                ("113(Win10pro03-n2)", "192.168.49.8"),
                ("114(Win10pro04-n2", "192.168.49.6"),
                ("115(Win10pro04-n2)", "192.168.49.9"),
                ("116(Win10pro04-n2)", "192.168.49.10"),
                ("225164(reporteFidelizacion", "192.168.48.225") 
            ]

            # 3.1 LISTA HIJAS VIX18
            ips_hijas_vix18 = [
                "192.168.49.76", "192.168.61.30", "192.168.61.50", "192.168.61.51",
                "192.168.61.31", "192.168.61.18", "192.168.61.43", "192.168.61.44",
                "192.168.61.45", "192.168.61.28", "192.168.61.42", "192.168.61.23",
                "192.168.61.5", "192.168.61.4", "192.168.51.204", "192.168.51.203",
                "192.168.51.202", "192.168.51.201", "192.168.51.195", "192.168.51.194",
                "192.168.51.193", "192.168.51.192", "192.168.51.191", "192.168.51.190",
                "192.168.51.189"
            ]

            # >>> chequeo inicial de soporte antes de escanear <<<
            if browser and page:
                check_and_handle_support_message(browser, page)

            for target_vmid, target_ip in lista_vms:
                # >>> chequeo soporte en cada iteración <<<
                if browser and page:
                    check_and_handle_support_message(browser, page)

                display_name = f"{target_vmid} (Agente)"
                visual_status = "unknown"

                if page:
                    try:
                        page.wait_for_selector(".x-grid-item", timeout=3000)
                        row_vm = page.locator(".x-grid-item").filter(has_text=re.compile(rf"^{target_vmid}\s")).first
                        if row_vm.is_visible():
                            full_text = row_vm.inner_text().split("\n")[0]
                            parts = full_text.split(" ", 1)
                            display_name = f"{parts[0]} {parts[1] if len(parts) > 1 else ''}"

                            row_html = row_vm.inner_html().lower()
                            if "stop" in row_html or "gray" in row_html:
                                visual_status = "stopped"
                            elif "play" in row_html or "running" in row_html:
                                visual_status = "running"
                    except:
                        pass

                print(f"    [INFO] ID: {display_name:<18} | Consultando {target_ip}...")

                if target_ip == "0.0.0.0":
                    status = "sin_agente"
                    resultado_txt = "Máquina Apagada o Sin Red (Sin IP)"
                elif visual_status == "stopped":
                    status = "sin_agente"
                    resultado_txt = "Máquina Apagada o Sin Red (Visual)"
                else:
                    status, resultado_txt = check_process_via_agent(target_ip)

                if status == "sin_proceso":
                    print(f"    [WARN] Inactivo. Comprobando arranque de bot...")
                    if start_bot_via_agent(target_ip):
                        time.sleep(12.0)
                        st_2, res_2 = check_process_via_agent(target_ip)
                        resultado_txt = (
                            f"Reactivado ({res_2.replace('Activo (', '').replace(')', '')})"
                            if st_2 == "activo" else "Fallo arranque"
                        )
                    else:
                        resultado_txt = "Error comando START"

                keywords = ["Fallo", "Error", "Sin", "Apagada", "Inaccesible", "Detenido", "No Inició"]
                
                # Lista de VMs a ignorar en Teams (Apagadas / No usadas)
                vms_ignoradas_teams = ["120", "130", "133", "165", "111", "161", "162", "163"]

                if any(k in resultado_txt for k in keywords):
                    # EXCLUIR VIGILANCIA VIX18 si aplica, y ahora blacklist específica
                    if str(target_vmid) not in vms_ignoradas_teams:
                         if "vix18" not in display_name.lower():
                            # REGLA 1: Solo reportar una vez al día
                            today_str = time.strftime("%Y-%m-%d")
                            alert_key = f"{target_ip}|{resultado_txt}|{today_str}"
                            
                            if alert_key not in ALERTS_SENT_CACHE:
                                msg_alerta = f"{display_name} | {target_ip} | {resultado_txt}"
                                if browser:
                                    sent_ok = send_teams_message(browser, msg_alerta, target_chat="logs_proxmox")
                                    if sent_ok:
                                        ALERTS_SENT_CACHE.add(alert_key)
                            else:
                                print(f"    [SILENCIO] Alerta ya enviada hoy para {target_ip}")
                    else:
                        print(f"    [SILENCIO TEAM] VM {target_vmid} ignorada intencionalmente.")


                print(f"{display_name:<24} | {target_ip:<15} | {resultado_txt}")

                if "130" in str(target_vmid) or "vix18" in display_name.lower():
                    print(f"\n    [INFO] VIX18 DETECTADA - Escaneando hijas...")
                    print("    " + "." * 50)
                    for ip_h in ips_hijas_vix18:
                        if browser and page:
                            check_and_handle_support_message(browser, page)

                        s_h, txt_h = check_process_via_agent(ip_h)
                        if s_h == "sin_proceso":
                            start_bot_via_agent(ip_h)
                            time.sleep(5)
                            _, txt_h = check_process_via_agent(ip_h)
                            txt_h = "Reactivado (Hija)"

                        print(f"    -> [HIJA] {ip_h:<15} | {txt_h}")
                    print("    " + "." * 50 + "\n")

                print("-" * 60)

            print(f"\n[ESPERA] Ciclo completado. Durmiendo 30 minutos...")

            # >>> dormir en chunks para seguir atendiendo mensajes de soporte <<<
            try:
                for _ in range(180):  # 180 * 10s = 30 min
                    if browser and page:
                        check_and_handle_support_message(browser, page)
                    time.sleep(10)
            except KeyboardInterrupt:
                break


if __name__ == "__main__":
    main()
