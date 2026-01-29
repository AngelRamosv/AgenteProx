from ping_checker import is_online
from teams_notifier import send_teams_message
import datetime

# Cambia esto por la IP real y el nombre real de la VM
IP_OBJETIVO = "192.168.49.151"
NOMBRE = "vix10"

def main():
    estado = "ONLINE" if is_online(IP_OBJETIVO) else "OFFLINE"
    hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mensaje = (
        f"🔍 Verificación de equipo Proxmox\n"
        f"Máquina: {NOMBRE}\n"
        f"IP: {IP_OBJETIVO}\n"
        f"Estado: {estado}\n"
        f"Hora: {hora}\n"
    )

    print("Enviando a Teams:\n", mensaje)
    send_teams_message(mensaje)
    print("Mensaje enviado.")

if __name__ == "__main__":
    main()
