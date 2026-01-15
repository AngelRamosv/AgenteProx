import subprocess

def is_online(ip: str, timeout: int = 2000) -> bool:
    
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout), ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return "TTL=" in result.stdout.upper()
    except Exception:
        return False
