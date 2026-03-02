from playwright.sync_api import sync_playwright
import time
import re
import sys
import config
import teams_bot
import vm_utils

def main():
    print("=" * 60)
    print(" AGENTE PROXMOX - MODO VIGILANCIA RPA")
    print("=" * 60 + "\n")

    # Cache local para logica de reportes diarios
    ALERTS_SENT_CACHE = set()

    with sync_playwright() as p:
        while True:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            msg_inicio = f"[{timestamp}] INICIANDO CICLO DE ESCANEO..."
            print(msg_inicio)
            print(f"{'VIX':<24} | {'IP':<15} | PROCESO")
            print("-" * 60)

            try:
                browser = p.chromium.connect_over_cdp(f"http://localhost:{config.DEBUG_PORT}")
                context = browser.contexts[0]
                page = None
                for pg in context.pages:
                    if ":8006" in pg.url.lower():
                        page = pg
                        break
                
                # Notificación de inicio de ciclo
                teams_bot.send_teams_message(browser, msg_inicio)

                if not page:
                    print("[ERROR] No se encontró pestaña Proxmox (:8006).")

                # Truco de Visibilidad
                try:
                    page.evaluate(
                        "Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: true}); "
                        "document.dispatchEvent(new Event('visibilitychange'));"
                    )
                except: pass
                
                try:
                    page.bring_to_front() 
                    time.sleep(0.5)
                except: pass

            except Exception as e:
                print(f"[ERROR] Conexión Navegador: {e}")
                page = None
                browser = None

            # >>> Chequeo INICIAL de soporte <<<
            if browser and page:
                vm_utils.check_and_handle_support_message(browser, page)

            # Iterar sobre la lista de config (Mucho mas limpio)
            for target_vmid, target_ip in config.LISTA_VMS:
                
                # >>> Chequeo INTERMEDIO (ciclo por VM) <<<
                if browser and page:
                    vm_utils.check_and_handle_support_message(browser, page)

                display_name = f"{target_vmid} (Agente)"
                visual_status = "unknown"

                if page:
                    try:
                        page.wait_for_selector(".x-grid-item", timeout=3000)
                        row_vm = page.locator(".x-grid-item").filter(has_text=re.compile(rf"^{re.escape(target_vmid.split()[0])}\s")).first
                        if row_vm.count() > 0 and row_vm.is_visible():
                            # Intentar leer nombre visual
                            # INTENTO DE LEER EL NOMBRE REAL (VIX) DESDE PROXMOX
                            try:
                                # Esto lee lo que Proxmox muestra en pantalla (Ej: "110 (vix21c)")
                                full_text = row_vm.inner_text().split("\n")[0]
                                display_name = full_text.strip()
                            except: 
                                display_name = str(target_vmid)

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
                    status, resultado_txt = vm_utils.check_process_via_agent(target_ip)

                if status == "sin_proceso":
                    print(f"    [WARN] Inactivo. Comprobando arranque de bot...")
                    if vm_utils.start_bot_via_agent(target_ip):
                        time.sleep(12.0)
                        st_2, res_2 = vm_utils.check_process_via_agent(target_ip)
                        resultado_txt = (
                            f"REINICIADO (Antes: {resultado_txt}) -> Ahora: {res_2}"
                        )
                    else:
                        resultado_txt = f"FALLO REINICIO (Antes: {resultado_txt})"

                # --- LÓGICA DE ALERTAS Y FILTROS (Full) ---
                # --- LÓGICA DE ALERTAS Y FILTROS (Definitiva) ---
                keywords = ["Fallo", "Error", "Sin", "Apagada", "Inaccesible", "Detenido", "No Inició"]
                
                # Limpieza de ID para comparaciones (ej: "120(vix...)" -> "120")
                current_id_clean = str(target_vmid).split('(')[0].strip()
                
                # Preparar blacklist limpia desde config
                blacklist_clean = [str(x).split('(')[0].strip() for x in config.VMS_IGNORADAS_TEAMS]

                if any(k in resultado_txt for k in keywords):
                    # EXCLUIR de Teams si el ID limpio está en la blacklist limpia
                    if current_id_clean not in blacklist_clean:
                         if "vix18" not in display_name.lower():
                            # REGLA: Solo reportar una vez al día
                            today_str = time.strftime("%Y-%m-%d")
                            alert_key = f"{target_ip}|{resultado_txt}|{today_str}"
                            
                            if alert_key not in ALERTS_SENT_CACHE:
                                msg_alerta = f"{display_name} | {target_ip} | {resultado_txt}"
                                if browser:
                                    sent_ok = teams_bot.send_teams_message(browser, msg_alerta, target_chat="logs_proxmox")
                                    if sent_ok:
                                        ALERTS_SENT_CACHE.add(alert_key)
                            else:
                                print(f"    [SILENCIO] Alerta ya enviada hoy para {target_ip}")
                    else:
                        print(f"    [SILENCIO TEAM] VM {target_vmid} ignorada intencionalmente.")

                print(f"{display_name:<24} | {target_ip:<15} | {resultado_txt}")

                # --- LOGICA VIX18 (Hijas) ---
                if "130" in str(target_vmid) or "vix18" in display_name.lower():
                    print(f"\n    [INFO] VIX18 DETECTADA - Escaneando hijas...")
                    print("    " + "." * 50)
                    for ip_h in config.IPS_HIJAS_VIX18:
                        if browser and page:
                            vm_utils.check_and_handle_support_message(browser, page)

                        s_h, txt_h = vm_utils.check_process_via_agent(ip_h)
                        if s_h == "sin_proceso":
                            vm_utils.start_bot_via_agent(ip_h)
                            time.sleep(5)
                            _, txt_h = vm_utils.check_process_via_agent(ip_h)
                            txt_h = "Reactivado (Hija)"

                        print(f"    -> [HIJA] {ip_h:<15} | {txt_h}")
                    print("    " + "." * 50 + "\n")

                print("-" * 60)

            print(f"\n[{time.strftime('%H:%M:%S')}] Escaneo completo. Esperando 30 minutos (Modo Vigilancia Soporte)...")
            
            # --- ESPERA ACTIVA (Soporte) ---
            try:
                for _ in range(180):  # 180 * 10s = 30 min (Restaurado)
                    if browser and page:
                        vm_utils.check_and_handle_support_message(browser, page)
                    time.sleep(10)
            except KeyboardInterrupt:
                break

if __name__ == "__main__":
    main()

