from flask import Flask, jsonify
import os
import psutil
import time

app = Flask(__name__)

# ==================== CONFIGURACIÓN ====================
PROCESOS_CRITICOS = ['chrome.exe', 'iexplore.exe', 'msedge.exe', 'javaw.exe', 'siebel.exe']
BAT_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "init - Acceso directo.lnk")
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

            p_name = (proc.info['name'] or "").lower()

            # Procesos críticos
            if p_name in PROCESOS_CRITICOS:
                mem_mb = proc.info['memory_info'].rss / (1024 * 1024)
                if mem_mb > MEMORIA_MINIMA_MB:
                    return True, p_name

            # Python bots (excluyendo este agente)
            if p_name in ['python.exe', 'pythonw.exe', 'py.exe']:
                cmdline = proc.info['cmdline'] or []
                es_agente = any(script_propio in (arg or "").lower() for arg in cmdline)
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

def detener_procesos_bot():
    """
    Detiene el bot matando procesos críticos + python bots (excepto el agente).
    Retorna lista de procesos terminados.
    """
    mi_pid = os.getpid()
    script_propio = os.path.basename(__file__).lower()
    terminados = []

    # 1) Intento suave (terminate)
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
        try:
            pid = proc.info['pid']
            if pid == mi_pid:
                continue

            name = (proc.info['name'] or "").lower()

            # Críticos con memoria > umbral
            if name in PROCESOS_CRITICOS:
                mem_mb = proc.info['memory_info'].rss / (1024 * 1024)
                if mem_mb > MEMORIA_MINIMA_MB:
                    proc.terminate()
                    terminados.append(f"{name}:{pid}")

            # Python bots (no el agente)
            if name in ['python.exe', 'pythonw.exe', 'py.exe']:
                cmdline = proc.info['cmdline'] or []
                es_agente = any(script_propio in (arg or "").lower() for arg in cmdline)
                if not es_agente:
                    proc.terminate()
                    terminados.append(f"{name}:{pid}")

        except:
            pass

    # 2) Espera breve
    time.sleep(2)

    # 3) Forzar kill si siguen vivos
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pid = proc.info['pid']
            if pid == mi_pid:
                continue

            name = (proc.info['name'] or "").lower()

            if name in PROCESOS_CRITICOS:
                proc.kill()

            if name in ['python.exe', 'pythonw.exe', 'py.exe']:
                cmdline = proc.info['cmdline'] or []
                es_agente = any(script_propio in (arg or "").lower() for arg in cmdline)
                if not es_agente:
                    proc.kill()
        except:
            pass

    return terminados

# ==================== ENDPOINTS HTTP ====================
@app.route('/status', methods=['GET'])
def check_status():
    activo, proceso = hay_procesos_activos()
    if activo:
        print(f"[HTTP] /status -> ACTIVO ({proceso})")
        return jsonify({"status": "activo", "procesos": [proceso]})
    else:
        print("[HTTP] /status -> SIN PROCESO")
        return jsonify({"status": "sin_proceso", "procesos": []})

@app.route('/start', methods=['POST'])
def start_bot():
    print("[HTTP] /start -> Comando recibido")
    if ejecutar_init():
        return jsonify({"result": "iniciado"})
    else:
        return jsonify({"result": "error"}), 404

# >>> NUEVO: STOP <<<
@app.route('/stop', methods=['POST'])
def stop_bot():
    print("[HTTP] /stop -> Comando recibido")
    terminados = detener_procesos_bot()
    # Confirmación rápida
    activo, proceso = hay_procesos_activos()
    if activo:
        return jsonify({"result": "parcial", "aun_activo": True, "proceso": proceso, "terminados": terminados}), 200
    return jsonify({"result": "detenido", "terminados": terminados}), 200
# ========================================================

if __name__ == '__main__':
    print("=" * 50)
    print("       AGENTE VM (SOLO ESPIA)")
    print("=" * 50)
    print(f"Archivo init: {BAT_PATH}")
    print(f"Existe: {os.path.exists(BAT_PATH)}")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5555)
