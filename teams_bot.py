from playwright.sync_api import sync_playwright
import time
import os
import re

import pytesseract
from PIL import Image
from collections import deque
import config

# ====== FIJA TESSERACT EN WINDOWS PROD (Simple) ======
# Ruta confirmada por usuario que funciona en local
TESS_BASE = r"C:\Program Files\Tesseract-OCR"

# Configuracion directa del ejecutable
pytesseract.pytesseract.tesseract_cmd = os.path.join(TESS_BASE, "tesseract.exe")

# Opcional: configurar TESSDATA_PREFIX si es necesario, apuntando a "tessdata"
tessdata_path = os.path.join(TESS_BASE, "tessdata")
if os.path.exists(tessdata_path):
    os.environ["TESSDATA_PREFIX"] = tessdata_path

# ===== Selectores estables Teams =====
SEL_MESSAGE = 'div[data-tid="chat-pane-message"]'
SEL_TEXT    = 'div[data-message-content] p'
SEL_IMAGE   = 'img[data-tid^="lazy-image"]'

# ===== Dedup por data-mid =====
_seen_mids = set()
_seen_q = deque(maxlen=500)

def _mark_mid(mid: str) -> bool:
    if not mid:
        return True
    if mid in _seen_mids:
        return False
    _seen_mids.add(mid)
    _seen_q.append(mid)
    if len(_seen_q) == _seen_q.maxlen:
        _seen_mids.clear()
        _seen_mids.update(_seen_q)
    return True

# ===== OCR Simplificado (Estilo usuario) =====
def ocr_tesseract_from_path(img_path: str) -> str:
    """
    Intento simple y directo usando PIL + Tesseract default.
    Coincide con la prueba exitosa del usuario.
    """
    try:
        # Uso directo de PIL
        img = Image.open(img_path)
        
        # OCR sin configs complejas (default suele funcionar bien para texto general)
        # Si se requiere, se puede agregar config='--psm 11' etc.
        text = pytesseract.image_to_string(img)
        
        # Limpieza basica
        text = re.sub(r'[^\x20-\x7E\n]', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text).strip()
        
        return text
    except Exception as e:
        print(f"    [OCR ERROR] {e}")
        return ""

def extract_ips(text: str):
    ips = re.findall(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', text)
    valid = []
    for ip in ips:
        parts = ip.split('.')
        try:
            if all(0 <= int(p) <= 255 for p in parts):
                valid.append(ip)
        except: pass
    return list(dict.fromkeys(valid))


def get_teams_page(browser):
    try:
        if not browser or not browser.contexts: return None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "teams.microsoft.com" in pg.url:
                    return pg
    except:
        pass
    return None

def teams_find_chat_item(page, name):
    import re
    pattern = re.compile(re.escape(name), re.IGNORECASE)
    
    candidates = [
        page.locator("div[role='treeitem']").filter(has_text=pattern).first,
        page.locator("li").filter(has_text=pattern).first,
        page.locator("span").filter(has_text=pattern).first,
    ]
    for loc in candidates:
        try:
            if loc.count() > 0:
                return loc
        except:
            pass
    return None


# ===== FUNCIÓN FINAL (INTEGRADA A TU FLUJO) =====
# Nota: Renombrada a read_latest_message_from_group para mantener compatibilidad
def read_latest_message_from_group(browser, group_name, page_proxmox=None):
    page = get_teams_page(browser)
    if not page: return None
    
    try:
        page.bring_to_front()
        time.sleep(0.3)
        
        # Navegacion al chat
        item = teams_find_chat_item(page, group_name)
        if not item: return None
        try: item.click(force=True)
        except: pass
        time.sleep(1.0)

        # Llama a la logica interna de ChatGTP
        result = read_last_message_text_plus_image_ocr(page)
        
        if not result:
            return None
            
        final_text = result["text"]
        
        # Volver contexto
        if page_proxmox:
            try: page_proxmox.bring_to_front()
            except: pass
            
        if final_text:
            print(f"    [TEAMS EXTRACT] \"{final_text[:60]}...\"")
            
        return final_text

    except Exception as e:
        print(f"[TEAMS ERROR] {e}")
        return None


# ===== IMPLEMENTACION INTERNA CHATGPT =====
def read_last_message_text_plus_image_ocr(page):
    try:
        try:
            page.wait_for_selector(SEL_MESSAGE, timeout=5000)
        except:
            return None

        last = page.locator(SEL_MESSAGE).last
        mid = last.get_attribute("data-mid") or ""

        if not _mark_mid(mid):
            return None

        parts = []

        # A) Texto
        txt_locator = last.locator(SEL_TEXT)
        if txt_locator.count() > 0:
            text_content = " ".join(txt_locator.all_inner_texts()).strip()
            if text_content:
                parts.append(text_content)

        # B) Imagen -> OCR
        img_locator = last.locator(SEL_IMAGE)
        ocr_text = ""
        img_path = "teams_latest.png"

        if img_locator.count() > 0:
            print("    [DEBUG] Imagen detectada (v3)...")
            img = img_locator.last

            try:
                img.scroll_into_view_if_needed(timeout=3000)
            except:
                pass
            page.wait_for_timeout(250)

            # 1) URL fullsize (prioriza gallery)
            url = None
            for _ in range(10):
                url = img.get_attribute("data-gallery-src") or img.get_attribute("data-orig-src")
                if url and not url.startswith("blob:"):
                    break
                page.wait_for_timeout(300)

            # 2) Intento descarga fullsize con timeout
            if url and not url.startswith("blob:"):
                try:
                    resp = page.request.get(url, timeout=6000)
                    if resp.ok:
                        with open(img_path, "wb") as f:
                            f.write(resp.body())
                        ocr_text = ocr_tesseract_from_path(img_path)
                except:
                    pass

            # 3) Fallback definitivo: visor (captura nítida de ESA imagen)
            if not ocr_text.strip():
                print("    [DEBUG] Fallback a Visor...")
                try:
                    gallery_id = img.get_attribute("data-gallery-id") or ""
                    img.click(timeout=3000)
                    page.wait_for_timeout(400)

                    if gallery_id:
                        viewer_img = page.locator(f'img[data-gallery-id="{gallery_id}"]').first
                    else:
                        viewer_img = page.locator('img[data-gallery-src], img[data-orig-src]').first

                    viewer_img.wait_for(state="visible", timeout=8000)
                    viewer_img.screenshot(path=img_path)

                    ocr_text = ocr_tesseract_from_path(img_path)

                    page.keyboard.press("Escape")
                except:
                    try:
                        page.keyboard.press("Escape")
                    except:
                        pass

        if ocr_text.strip():
            parts.append(f"[OCR: {ocr_text.strip()}]")

        final_text = " ".join(parts).strip()
        if not final_text:
            final_text = last.inner_text()

        ips = extract_ips(final_text)

        return {"mid": mid, "text": final_text, "ips": ips}
    except Exception as e:
        print(f"    [TEAMS INTERNAL ERROR] {e}")
        return None

def send_teams_message(browser, message, target_chat="logs_proxmox"):
    try:
        page_teams = get_teams_page(browser)
        if not page_teams:
            return False 

        print(f"    [TEAMS] Enviando alerta para: {message.split('|')[0]}...")
        page_teams.bring_to_front()
        time.sleep(0.5)

        if target_chat:
            chat_item = teams_find_chat_item(page_teams, target_chat)
            if chat_item:
                chat_item.click(force=True)
                time.sleep(1.0)
            else:
                if target_chat == "logs_proxmox" and config.TEAMS_CHANNEL_URL:
                     page_teams.goto(config.TEAMS_CHANNEL_URL)
                     time.sleep(3.0)
        
        input_box = page_teams.locator("div[contenteditable='true'], div[data-tid='ckeditor']").first
        if input_box.is_visible(timeout=5000):
            input_box.click(force=True)
            input_box.fill(message)
            page_teams.keyboard.press("Enter")
            time.sleep(0.5)
            return True
        else:
            return False
    except Exception as e:
        print(f"    [TEAMS EXCEPTION] {e}")
        return False
