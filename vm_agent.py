from flask import Flask, jsonify
import os
import psutil

app = Flask(__name__)

# ==================== CONFIGURACIÓN ====================
# Procesos que indican que el bot está activo
PROCESOS_CRITICOS = ['chrome.exe', 'iexplore.exe', 'msedge.exe', 'javaw.exe', 'siebel.exe']

# Archivo a ejecutar cuando no hay procesos
BAT_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "init - Acceso directo.lnk")

# Memoria mínima en MB para Chrome/Java (evita zombies)
MEMORIA_MINIMA_MB = 40
# ========================================================

def hay_procesos_activos():
    """Revisa si hay algún proceso crítico corriendo."""
    mi_pid = os.getpid()
    script_propio = os.path.basename(__file__).lower()
    
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
        try:
            if proc.info['pid'] == mi_pid:
                continue
            
            p_name = proc.info['name'].lower()
            
            # Detectar procesos críticos (Chrome, Java, Siebel, etc.)
            if p_name in PROCESOS_CRITICOS:
                mem_mb = proc.info['memory_info'].rss / (1024 * 1024)
                if mem_mb > MEMORIA_MINIMA_MB:
                    return True, p_name
            
            # Detectar Python (excluyendo este agente)
            if p_name in ['python.exe', 'pythonw.exe', 'py.exe']:
                cmdline = proc.info['cmdline'] or []
                es_agente = False
                for arg in cmdline:
                    if script_propio in arg.lower():
                        es_agente = True
                        break
                if not es_agente:
                    return True, "python_bot"
                    
        except:
            pass
    
    return False, None

def ejecutar_init():
    """Ejecuta el archivo init."""
    if os.path.exists(BAT_PATH):
        print(f"[EJECUTANDO] {BAT_PATH}")
        os.system(f'start "" "{BAT_PATH}"')
        return True
    else:
        print(f"[ERROR] No existe: {BAT_PATH}")
        return False

# ==================== ENDPOINTS HTTP ====================
@app.route('/status', methods=['GET'])
def check_status():
    """El RPA consulta este endpoint para saber el estado."""
    activo, proceso = hay_procesos_activos()
    
    if activo:
        print(f"[HTTP] /status -> ACTIVO ({proceso})")
        return jsonify({"status": "activo", "procesos": [proceso]})
    else:
        print("[HTTP] /status -> SIN PROCESO")
        return jsonify({"status": "sin_proceso", "procesos": []})

@app.route('/start', methods=['POST'])
def start_bot():
    """El RPA envía este comando para forzar el inicio."""
    print("[HTTP] /start -> Comando recibido")
    
    if ejecutar_init():
        return jsonify({"result": "iniciado"})
    else:
        return jsonify({"result": "error"}), 404
# ========================================================

if __name__ == '__main__':
    print("=" * 50)
    print("       AGENTE VM (SOLO ESPIA)")
    print("=" * 50)
    print(f"Archivo init: {BAT_PATH}")
    print(f"Existe: {os.path.exists(BAT_PATH)}")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5555)
