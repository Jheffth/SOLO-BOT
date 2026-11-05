"""A ponte: liga o bot da VPS às TVs de casa sem abrir nenhuma porta no roteador.

Roda no notebook (mesma rede das TVs). Faz só conexões de SAÍDA para o bot:
busca o próximo comando (long-poll autenticado), valida, executa na TV e devolve
o resultado. Cada passo fica registrado em ponte.log.

  python ponte.py
"""
import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx

import lgtv

LOG = Path(__file__).with_name("ponte.log")
log = logging.getLogger("ponte_tv")


def _configurar_log():
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # console do Windows sem UTF-8
    except (AttributeError, ValueError):
        pass
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    arquivo = RotatingFileHandler(LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    tela = logging.StreamHandler()
    for h in (arquivo, tela):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def _destino():
    cfg = lgtv.carregar_config()
    ponte = cfg.get("ponte", {})
    url = (os.environ.get("PONTE_TV_URL") or ponte.get("url") or "").rstrip("/")
    token = os.environ.get("PONTE_TV_TOKEN") or ponte.get("token") or ""
    if not url or not token:
        raise SystemExit("Falta o endereço do bot ou o token: rode `python tv.py token <url do bot>`.")
    if not url.startswith("https://") and "localhost" not in url and "127.0.0.1" not in url:
        raise SystemExit("Use https:// para o bot (o token não pode viajar sem criptografia).")
    return url, token, sorted(cfg.get("tvs", {}))


async def _atender(cmd):
    """Valida e executa um comando recebido. Nunca deixa uma exceção derrubar a ponte."""
    acao, tv = cmd.get("acao"), cmd.get("tv")
    try:
        if acao not in lgtv.ACOES:
            raise lgtv.ErroTV(f"Ação não permitida: {acao}.")
        r = await lgtv.executar(acao, cmd.get("args") or {}, apelido=tv)
        return True, r["mensagem"]
    except lgtv.ErroTV as ex:
        return False, str(ex)
    except Exception:
        log.exception("erro inesperado em %s", acao)
        return False, "Erro inesperado na ponte; veja ponte.log no notebook."


async def rodar():
    url, token, tvs = _destino()
    cabecalho = {"Authorization": f"Bearer {token}"}
    log.info("ponte ligada → %s · TVs: %s", url, ", ".join(tvs) or "nenhuma")
    pausa = 2
    async with httpx.AsyncClient(headers=cabecalho, timeout=httpx.Timeout(10, read=40)) as http:
        while True:
            try:
                r = await http.get(f"{url}/api/ponte-tv/proximo", params={"espera": 25, "tvs": ",".join(tvs)})
                if r.status_code == 204:
                    pausa = 2
                    continue
                if r.status_code in (401, 404):
                    log.error("o bot recusou a ponte (%s): confira o token e PONTE_TV_TOKEN no servidor", r.status_code)
                    await asyncio.sleep(60)
                    continue
                r.raise_for_status()
                cmd = r.json()
                log.info("comando #%s %s %s tv=%s", cmd.get("id"), cmd.get("acao"), cmd.get("args") or "", cmd.get("tv") or "padrão")
                ok, mensagem = await _atender(cmd)
                log.info("resultado #%s ok=%s %s", cmd.get("id"), ok, mensagem)
                await http.post(f"{url}/api/ponte-tv/resultado", json={"id": cmd["id"], "ok": ok, "mensagem": mensagem})
                pausa = 2
            except (httpx.HTTPError, ValueError) as ex:
                log.warning("sem conexão com o bot (%s); nova tentativa em %ss", type(ex).__name__, pausa)
                await asyncio.sleep(pausa)
                pausa = min(pausa * 2, 60)


if __name__ == "__main__":
    _configurar_log()
    try:
        asyncio.run(rodar())
    except KeyboardInterrupt:
        log.info("ponte desligada")
