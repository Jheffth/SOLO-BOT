"""Descobre TVs LG webOS na rede local (somente biblioteca padrão).
Uso: python descobrir_lg.py
"""
import socket, concurrent.futures as cf, re

def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    finally:
        s.close()

def ssdp(timeout=4):
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n').encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    s.sendto(msg, ("239.255.255.250", 1900))
    achados = {}
    try:
        while True:
            data, addr = s.recvfrom(65507)
            achados.setdefault(addr[0], []).append(data.decode(errors="ignore"))
    except socket.timeout:
        pass
    return achados

def porta_aberta(ip, porta, t=0.4):
    try:
        with socket.create_connection((ip, porta), timeout=t):
            return True
    except OSError:
        return False

def varredura(base):
    ips = [f"{base}.{i}" for i in range(1, 255)]
    with cf.ThreadPoolExecutor(100) as ex:
        r = list(ex.map(lambda ip: (ip, porta_aberta(ip, 3000), porta_aberta(ip, 3001)), ips))
    return [(ip, a, b) for ip, a, b in r if a or b]

if __name__ == "__main__":
    meu = ip_local()
    print("Seu IP:", meu)
    print("\n[1] SSDP (anúncios na rede)...")
    for ip, respostas in ssdp().items():
        txt = " ".join(respostas)
        if re.search(r"lg|webos", txt, re.I):
            print("  Possível LG:", ip)
    print("\n[2] Varredura das portas 3000/3001 (webOS)...")
    achados = varredura(".".join(meu.split(".")[:3]))
    for ip, p3000, p3001 in achados:
        print(f"  {ip}  3000={'aberta' if p3000 else '-'}  3001={'aberta' if p3001 else '-'}")
    if not achados:
        print("  Nada encontrado. Confirme que a TV está ligada e no mesmo Wi-Fi.")
