from playwright.sync_api import sync_playwright
import time

DEBUG_PORT = 9222

def main():
    print("--- INICIANDO DIAGNOSTICO ---")
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    except Exception as e:
        print(f"Error conectando: {e}")
        return

    page = None
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "proxmox" in pg.url.lower() or "192.168" in pg.url:
                page = pg
                break
        if page: break

    if not page:
        print("No se encontró la pestaña Proxmox.")
        return

    try: page.bring_to_front()
    except: pass
    
    # 1. Analizar Filtro
    print("\n[1] BUSCANDO INPUT DE FILTRO:")
    filters = page.locator("input").all()
    found_filter = False
    for i, f in enumerate(filters):
        try:
            if not f.is_visible(): continue
            ph = f.get_attribute("placeholder")
            cls = f.get_attribute("class")
            if ph and ("Filter" in ph or "Buscar" in ph):
                print(f"   -> ENCONTRADO: Index {i} | Placeholder: '{ph}' | Class: '{cls}'")
                found_filter = True
                # Intentar limpiar y escribir '120'
                f.click()
                f.fill("120")
                time.sleep(1)
                print("   -> Prueba: Escribí '120' en el filtro.")
                break
        except: pass
    
    if not found_filter:
        print("   -> [ALERTA] No se encontró ningún input que parezca el filtro.")

    # 2. Analizar Árbol (Visibilidad de Nodos)
    print("\n[2] ANALIZANDO NODOS DEL ARBOL (VM 120):")
    # Buscamos nodos que contengan '120'
    xpath = "//span[contains(@class,'x-tree-node-text') and contains(text(), '120')]"
    nodes = page.locator(xpath).all()
    print(f"   -> Nodos encontrados con texto '120': {len(nodes)}")
    
    for i, n in enumerate(nodes):
        try:
            txt = n.inner_text()
            vis = n.is_visible()
            box = n.bounding_box()
            print(f"   Node {i}: Text='{txt}' | Visible={vis} | Box={box}")
            
            if vis:
                print("   -> Intentando CLIC en este nodo...")
                n.click(timeout=2000, force=True)
                print("   -> Clic realizado.")
                time.sleep(1)
        except Exception as e:
            print(f"   -> Error inspeccionando nodo {i}: {e}")

    # 3. Verificar si cargó el Summary
    print("\n[3] VERIFICANDO CARGA DE PANEL (Header):")
    try:
        header = page.locator("div").filter(has_text="Virtual Machine 120").first
        if header.count() > 0:
            print(f"   -> HEADER DETECTADO: {header.inner_text()}")
        else:
            print("   -> HEADER NO DETECTADO para VM 120.")
    except: pass

    # 4. Dump HTML parcial del árbol
    print("\n[4] DUMP HTML DEL CONTENEDOR DEL ARBOL:")
    try:
        tree_view = page.locator(".x-tree-view").first
        html = tree_view.inner_html()
        # Guardar en archivo para yo leerlo
        with open("tree_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("   -> Guardado en 'tree_dump.html' (Primeros 500 chars):")
        print(html[:500])
    except Exception as e:
        print(f"   -> Error dump: {e}")

    p.stop()
    print("\n--- DIAGNOSTICO TERMINADO ---")

if __name__ == "__main__":
    main()
