# Configuracion Global
# ==================

DEBUG_PORT = 9222
AGENT_PORT = 5555
AGENT_TIMEOUT = 5

# Teams
TEAMS_CHANNEL_URL = "https://teams.microsoft.com/l/channel/19%3A0113cb42e12f407fb933b4b1ac742dca%40thread.tacv2/logs_proxmox?groupId=9300d12e-bf09-4717-aefd-bc1a35d87fac&tenantId=caca42e2-ad4a-4d19-824c-3ff3709bd840"
TEAMS_SUPPORT_GROUP_NAME = "Miguel Angel Ramos Castellanos"

# Criterios de Analisis (Soporte)
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

# Criterios Regex
CRITERIOS_REGEX = [
    # --- Negaciones / Fallos explícitos ---
    r"no.*registro",       # "no toma registros", "no registro"
    r"sin.*registro",      # "sin registros"
    r"no.*conecta",        # "no se conecta", "no conectada"
    r"sin.*conexi",        # "sin conexión"
    r"no.*toma",           # "no toma", "no está tomando"
    r"falta.*registro",    # "faltan registros"
    r"deten.*proceso",     # "detenido el proceso"
    
    # --- Solicitudes de Acción (Verbos) ---
    r"revisar",            # "favor de revisar", "pueden revisar"
    r"checar",             # "pueden checar", "chequen"
    r"validar",            # "validar ip"
    r"verificar",          # "verificar esta ip"
    
    # --- Solicitudes de Ayuda (LO QUE FALTABA) ---
    r"apoyo",              # "apoyo con esta ip"
    r"ayuda",              # "ayuda con...", "ayudar a..."
    
    # --- Acciones Técnicas ---
    r"conectar",           # "ayudar a conectar", "para conectar"
    r"reinic",             # "reiniciar", "reinicio"
    
    # --- Estados de Error ---
    r"falla",              # "tengo falla", "fallando"
    r"error",              # "marca error"
    r"traba",              # "se trabó", "trabada"
    r"colga",              # "colgada", "se colgó"
    r"pasm",               # "pasmada"
]

# Cache
LAST_TEAMS_HASH = None
ALERTS_SENT_CACHE = set()

# LISTAS DE MAQUINAS
# ==================
LISTA_VMS = [
    ("110(vix21c)", "192.168.49.109"),
    ("120(vix32)", "192.168.49.76"),
    ("121(vix10)", "192.168.49.151"),
    ("123(vix11)", "192.168.49.21"),
    ("124(vix12)", "192.168.49.22"),
    ("125(vix13)", "192.168.51.164"),
    ("126(vix14)", "192.168.49.31"),
    ("127(vix15)", "192.168.49.25"),
    ("128(vix16)", "192.168.49.26"),
    ("129(vix17)", "192.168.49.127"),
    ("130(vix18)", "192.168.49.28"),
    ("131(vix19)", "192.168.49.29"),
    ("132(vix20)", "192.168.49.30"),
    ("133(vix21)", "192.168.49.33"),
    ("134(Equipo1)", "192.168.51.13"),
    ("135(vix22)", "192.168.51.48"),
    ("136(vix23)", "192.168.51.183"),
    ("137(vix24)", "192.168.49.36"),
    ("138(vix25)", "192.168.49.37"),
    ("139(vix26)", "192.168.49.57"),
    ("140(vix27)", "192.168.49.58"),
    ("141(vix28)", "192.168.49.40"),
    ("142(vix29)", "192.168.50.49"),
    ("143(Equipo2)", "192.168.51.14"),
    ("144(vix31)", "192.168.49.43"),
    ("145(vix21)", "192.168.49.90"),
    ("165(reporteFidelizacion)", "192.168.48.225"),
    ("167(Equipo3)", "192.168.51.16"),
    ("168(Equipo4)", "192.168.51.17"),
    ("169(Equipo5)", "192.168.51.20"),
    ("170(Equipo6)", "192.168.51.28"),
    ("171(Equipo7)", "192.168.51.30"),
    ("172(Equipo8)", "192.168.51.44"),
    ("111(VIX33)", "0.0.0.0"),
    ("146(vix33)", "192.168.49.77"),
    ("147(vix34)", "192.168.49.78"),
    ("148(vix35)", "192.168.49.79"),
    ("149(vix36)", "192.168.49.80"),
    ("150(vix37)", "192.168.49.81"),
    ("151(vix38)", "192.168.49.82"),
    ("152(vix39)", "192.168.49.83"),
    ("153(vix40)", "192.168.49.84"),
    ("154(vix41)", "192.168.49.86"),
    ("155(vix42)", "192.168.49.87"),
    ("156(vix43)", "192.168.51.88"),
    ("157(vix44)", "192.168.51.89"),
    ("158(vix45)", "192.168.51.90"),
    ("159(vix46)", "192.168.51.91"),
    ("160(47RAM)", "192.168.48.91"),
    ("161(AzRAM)", "192.168.48.224"),
    ("162(6Ram)", "192.168.51.57"),
    ("163(izziFtp)", "192.168.50.37"),
    ("164(reporteFidelizacion)", "192.168.48.225"),
    ("110 (Equipo19)", "192.168.49.94"), 
    ("113(Win10pro03-n2)", "192.168.49.8"),
    ("114(Win10pro04-n2", "192.168.49.6"),
    ("115(Win10pro04-n2)", "192.168.49.9"),
    ("116(Win10pro04-n2)", "192.168.49.10"),
    ("117(Win10pro04-n2)", "192.168.49.11"),
    ("118(Win10pro04-n2)", "192.168.49.12"),
    ("119(Win10pro-maquina35)", "192.168.49.93"),
    ("122(Win10pro04-n2)", "192.168.49.13")
]

IPS_HIJAS_VIX18 = [
    "192.168.49.76", "192.168.61.30", "192.168.61.50", "192.168.61.51",
    "192.168.61.31", "192.168.61.18", "192.168.61.43", "192.168.61.44",
    "192.168.61.45", "192.168.61.28", "192.168.61.42", "192.168.61.23",
    "192.168.61.5", "192.168.61.4", "192.168.51.204", "192.168.51.203",
    "192.168.51.202", "192.168.51.201", "192.168.51.195", "192.168.51.194",
    "192.168.51.193", "192.168.51.192", "192.168.51.191", "192.168.51.190",
    "192.168.51.189"
]

# LISTA NEGRA: VMs que NO enviaran alerta a Teams (Apagadas / No usadas)
# IDs deben coincidir con el primer elemento de la tupla en LISTA_VMS (sin texto extra)
VMS_IGNORADAS_TEAMS = ["120(vix21c)", "130(vix18)", "133(vix21)", "165(Fidelizaciòn)", "111(vix33)", "161(AzRpa)", "162(6Ram)", "163(izziFtp)"]

# Criterios Regex

# Lista de respuestas aleatorias 
RESPUESTAS_SOPORTE = [
    "Un momento, se revisa el equipo",
    "Recibido ya lo estamos atendiendo",
    "Enterado lo validamos en un momento",
    "Si lo revisamos",
    "Claro se valida",
    "Lo checo", 
    "Enseguida lo revisamos",
    "Ok, ya lo estamos viendo",
    "Entendido, lo checamos ahora",
    "Ya lo estamos atendiendo",
    "Se revisa"
]