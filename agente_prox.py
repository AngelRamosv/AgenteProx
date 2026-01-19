from playwright.sync_api import sync_playwright
import time
import requests
import re
import sys 
import subprocess
import platform

# Configuración
DEBUG_PORT = 9222
AGENT_PORT = 5555
AGENT_TIMEOUT = 5

# URL del canal logs_proxmox (Referencia)
TEAMS_CHANNEL_URL = "https://teams.microsoft.com/l/channel/19%3A0113cb42e12f407fb933b4b1ac742dca%40thread.tacv2/logs_proxmox?groupId=9300d12e-bf09-4717-aefd-bc1a35d87fac&tenantId=caca42e2-ad4a-4d19-824c-3ff3709bd840"

def is_pingable(ip):
    """Verifica si la máquina responde a Ping (ICMP)."""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    cmd = ['ping', param, '1', ip]
    try:
        # Timeout corto para no alentar el escaneo masivo
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except:
        return False

def check_process_via_agent(ip):
    """Consulta directa al agente con Diagnóstico Avanzado (Ping vs Puerto)."""
    url = f"http://{ip}:{AGENT_PORT}/status"
    # Configurar para IGNORAR PROXIES del sistema (Clave para IPs internas)
    no_proxy = {"http": None, "https": None}
    
    # INTENTO 1
    try:
        response = requests.get(url, timeout=AGENT_TIMEOUT, proxies=no_proxy)
        if response.status_code == 200:
            data = response.json()
            procs = data.get("procesos", [])
            if procs: return "activo", f"Activo ({', '.join(procs)})"
            else: return "sin_proceso", "Sin procesos RPA corriendo"
        return "error_status", "Agente responde pero status no 200"
    
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
        # INTENTO 2 (RETRY ROBUSTO NO PROXY)
        try:
            time.sleep(2.0) 
            response = requests.get(url, timeout=10, proxies=no_proxy)
            if response.status_code == 200:
                data = response.json()
                procs = data.get("procesos", [])
                if procs: return "activo", f"Activo ({', '.join(procs)}) [Retry]"
                else: return "sin_proceso", "Sin procesos RPA corriendo [Retry]"
        except:
             # FALLÓ RETRY -> AQUÍ HACEMOS EL DIAGNÓSTICO
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
        # Ignorar proxy tambien aqui
        res = requests.post(url, timeout=AGENT_TIMEOUT, proxies={"http": None, "https": None})
        return res.status_code == 200
    except: return False

def send_teams_message(browser, message):
    """Busca la pestaña de Teams y escribe el mensaje en el chat activo."""
    try:
        page_teams = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "teams.microsoft.com" in pg.url:
                    page_teams = pg
                    break
            if page_teams: break
        
        if not page_teams:
            print("    [TEAMS ERROR] No se encontró pestaña de Teams abierta.")
            return False 

        print(f"    [TEAMS] Enviando alerta para: {message.split('|')[0]}...")
        page_teams.bring_to_front()
        time.sleep(0.5)
        
        input_box = page_teams.locator("div[contenteditable='true'], div[data-tid='ckeditor']").first
        if input_box.is_visible(timeout=5000): # Aumento timeout a 5s
            input_box.click(force=True)
            input_box.fill(message)
            page_teams.keyboard.press("Enter")
            time.sleep(0.5)
            # Regresar focus podría ser opcional
            return True
        else:
            print("    [TEAMS ERROR] No se encontró cuadro de texto (Chat no seleccionado).")
            return False
    except Exception as e:
        print(f"    [TEAMS EXCEPTION] {e}")
        return False

def main():
    print("=" * 60)
    print(" AGENTE PROXMOX - MODO VIGILANCIA RPA")
    print("=" * 60 + "\n")

    while True: # BUCLE INFINITO
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        msg_inicio = f"[{timestamp}] INICIANDO CICLO DE ESCANEO..."
        print(msg_inicio)
        print(f"{'VIX':<24} | {'IP':<15} | PROCESO")
        print("-" * 60)

        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
                context = browser.contexts[0]
                page = None
                for pg in context.pages:
                    if ":8006" in pg.url.lower(): page = pg; break
                
                # Intentamos enviar el mensaje de INICIO a Teams
                send_teams_message(browser, msg_inicio)

                if not page:
                    print("[ERROR] No se encontró pestaña Proxmox (:8006).")

                # Anti-throttling
                try: page.evaluate("Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: true}); document.dispatchEvent(new Event('visibilitychange'));")
                except: pass
                try: page.bring_to_front(); time.sleep(0.5)
                except: pass

            except Exception as e:
                print(f"[ERROR] Conexión Navegador: {e}")
                page = None 

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
                ("164", "192.168.48.225")
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

            for target_vmid, target_ip in lista_vms:
                # -- Nombre Visual y ESTADO --
                display_name = f"{target_vmid} (Agente)"
                visual_status = "unknown"
                
                if page:
                    try:
                        # Aumentamos timeout para asegurar lectura de nombres
                        page.wait_for_selector(".x-grid-item", timeout=3000)
                        row_vm = page.locator(".x-grid-item").filter(has_text=re.compile(rf"^{target_vmid}\s")).first
                        if row_vm.is_visible():
                            full_text = row_vm.inner_text().split("\n")[0]
                            parts = full_text.split(" ", 1)
                            display_name = f"{parts[0]} {parts[1] if len(parts)>1 else ''}"
                            
                            # Estado Visual para Desempate
                            row_html = row_vm.inner_html().lower()
                            if "stop" in row_html or "gray" in row_html:
                                visual_status = "stopped"
                            elif "play" in row_html or "running" in row_html:
                                visual_status = "running"
                    except: pass

                # -- Consulta Agente --
                print(f"    [INFO] ID: {display_name:<18} | Consultando {target_ip}...")
                
                # Caso especial 0.0.0.0 (111)
                if target_ip == "0.0.0.0":
                    status = "sin_agente"
                    resultado_txt = "Máquina Apagada o Sin Red (Sin IP)"
                
                # Caso Apagado Visual (Anula ping fantasma)
                elif visual_status == "stopped":
                    status = "sin_agente"
                    resultado_txt = "Máquina Apagada o Sin Red (Visual)"
                
                else:
                    status, resultado_txt = check_process_via_agent(target_ip)
                
                # -- Remediar --
                if status == "sin_proceso":
                    print(f"    [WARN] Inactivo. Comprobando arranque (12s)...")
                    if start_bot_via_agent(target_ip):
                        time.sleep(12.0)
                        st_2, res_2 = check_process_via_agent(target_ip)
                        resultado_txt = f"Reactivado ({res_2.replace('Activo (', '').replace(')', '')})" if st_2 == "activo" else "Fallo arranque"
                    else:
                        resultado_txt = "Error comando START"

                # NOTIFICAR FALLAS A TEAMS (Solo resultado final)
                # Formato solicitado: ID (Nombre) | IP | Error
                # Corrección: "Inició" coincide con "NO Inició", "Sin" con "Sin conexión", etc.
                keywords = ["Fallo", "Error", "Sin", "Apagada", "Inaccesible", "Detenido", "No Inició"]
                if any(k in resultado_txt for k in keywords):
                     # EXCLUIR VIX18 TEMPORALMENTE
                     if "vix18" not in display_name.lower():
                         msg_alerta = f"{display_name} | {target_ip} | {resultado_txt}"
                         send_teams_message(browser, msg_alerta)
                
                print(f"{display_name:<24} | {target_ip:<15} | {resultado_txt}")

                # -- SUB-ESCANEO VIX18 --
                if "130" in str(target_vmid) or "vix18" in display_name.lower():
                    print(f"\n    [INFO] VIX18 DETECTADA - Escaneando hijas...")
                    print("    " + "."*50)
                    for ip_h in ips_hijas_vix18:
                        s_h, txt_h = check_process_via_agent(ip_h)
                        # Remediar hija
                        if s_h == "sin_proceso":
                             start_bot_via_agent(ip_h); time.sleep(5)
                             _, txt_h = check_process_via_agent(ip_h)
                             txt_h = "Reactivado (Hija)"
                        
                        # Notificar también hijas si fallan (TEMPORALMENTE COMENTADO)
                        # if any(k in txt_h for k in keywords):
                        #      send_teams_message(browser, f"[VIX18 HIJA] {ip_h} | {txt_h}")

                        print(f"    -> [HIJA] {ip_h:<15} | {txt_h}")
                    print("    " + "."*50 + "\n")

                print("-" * 60)

        print(f"\n[ESPERA] Ciclo completado. Durmiendo 30 minutos...")
        try:
            time.sleep(1800) # 30 min
        except KeyboardInterrupt:
            # Notificar detención?
            break

if __name__ == "__main__":
    main()
