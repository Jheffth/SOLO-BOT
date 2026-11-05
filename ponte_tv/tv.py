"""Linha de comando para parear e testar a TV sem passar pelo bot.

  python tv.py parear sala 192.168.1.13 f0:86:20:f2:26:1e
  python tv.py sala volume definir 15
  python tv.py sala abrir_app youtube
  python tv.py sala aviso "Oi da Bella"
  python tv.py lista
  python tv.py token https://solobot.duckdns.org   (gera o token da ponte)
"""
import asyncio
import secrets
import sys

import lgtv


def _args(acao, resto):
    if acao == "volume":
        return {"modo": resto[0] if resto else "", "valor": resto[1] if len(resto) > 1 else None}
    if acao == "abrir_app":
        return {"app": resto[0] if resto else ""}
    if acao == "entrada":
        return {"hdmi": resto[0] if resto else ""}
    if acao == "aviso":
        return {"texto": " ".join(resto)}
    return {}


async def principal(argv):
    if len(argv) >= 4 and argv[0] == "parear":
        print("Aceite o pedido que vai aparecer na TV (você tem 90 segundos)...")
        r = await lgtv.parear(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else "")
        print(f"Pareada: {r['apelido']} ({r['webos']}). Chave guardada em {lgtv.CONFIG.name}.")
        return 0
    if argv[:1] == ["lista"]:
        cfg = lgtv.carregar_config()
        for nome, tv in cfg.get("tvs", {}).items():
            marca = " (padrão)" if nome == cfg.get("padrao") else ""
            print(f"{nome}{marca}: {tv['ip']}  {tv['mac']}  {tv.get('modelo', '')}  "
                  f"{'pareada' if tv.get('client_key') else 'sem pareamento'}")
        return 0
    if len(argv) == 2 and argv[0] == "token":
        cfg = lgtv.carregar_config()
        token = secrets.token_urlsafe(32)
        cfg["ponte"] = {"url": argv[1].rstrip("/"), "token": token}
        lgtv.salvar_config(cfg)
        print("Token salvo em tv_config.json. Coloque a mesma linha no .env do Solo Bot na VPS:")
        print(f"PONTE_TV_TOKEN={token}")
        return 0
    if len(argv) >= 2:
        r = await lgtv.executar(argv[1], _args(argv[1], argv[2:]), apelido=argv[0])
        print(r["mensagem"])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(principal(sys.argv[1:])))
    except lgtv.ErroTV as ex:
        print("Erro:", ex)
        sys.exit(1)
