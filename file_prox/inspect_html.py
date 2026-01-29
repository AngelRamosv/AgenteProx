from playwright.sync_api import sync_playwright
import json

DEBUG_PORT = 9222

def inspect_html_structure(page):
    """Inspecciona la estructura HTML del panel Summary."""
    
    # Hacer clic en la primera VM
    first_vm = page.locator('.x-tree-node-text').first
    vm_text = first_vm.inner_text()
    print(f"[INFO] Haciendo clic en: {vm_text}\n")
    first_vm.click()
    
    import time
    time.sleep(3)
    
    # Obtener TODO el HTML del panel Summary
    html_content = page.content()
    
    # Guardar HTML completo
    with open('proxmox_panel.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("[OK] HTML guardado en: proxmox_panel.html")
    
    # Buscar todos los divs que contengan IPs
    js = """
    () => {
        const allElements = document.querySelectorAll('*');
        const results = [];
        
        for (let el of allElements) {
            const text = el.textContent;
            if (text && text.match(/\\b192\\.168\\.\\d{1,3}\\.\\d{1,3}\\b/)) {
                results.push({
                    tag: el.tagName,
                    id: el.id,
                    className: el.className,
                    text: text.substring(0, 100),
                    innerHTML: el.innerHTML.substring(0, 200)
                });
            }
        }
        
        return results;
    }
    """
    
    elements_with_ip = page.evaluate(js)
    
    print(f"\n[INFO] Elementos que contienen IPs: {len(elements_with_ip)}\n")
    
    for i, el in enumerate(elements_with_ip[:10]):  # Mostrar solo los primeros 10
        print(f"Elemento {i+1}:")
        print(f"  Tag: {el['tag']}")
        print(f"  ID: {el['id']}")
        print(f"  Class: {el['className']}")
        print(f"  Texto: {el['text'][:80]}")
        print()

def main():
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    
    page = None
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if 'proxmox' in pg.url.lower() or '192.168' in pg.url:
                page = pg
                break
        if page:
            break
    
    if not page:
        print("[ERROR] No se encontró Proxmox")
        return
    
    inspect_html_structure(page)
    
    browser.close()
    p.stop()

if __name__ == "__main__":
    main()
