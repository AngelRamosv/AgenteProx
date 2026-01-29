import pyautogui
import time

def send_teams_message(message: str):
    """
    Escribe el mensaje en la ventana ACTUAL (Teams) y presiona Enter.
    Tienes unos segundos para enfocar Teams después de lanzar el script.
    """
    # Pausa para que tengas tiempo de ir a la ventana de Teams
    time.sleep(3)

    # Escribir el mensaje
    pyautogui.typewrite(message)

    # Enviar
    pyautogui.press("enter")
