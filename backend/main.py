# -*- coding: utf-8 -*-
"""Solo Bot — um bot, vários sistemas."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
from database import criar_tabelas
from routers import admin, auth, conectar, conta, interno, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FRONT = Path(__file__).resolve().parent.parent / "frontend"

async def _buscar_manifestos_sempre():
    """De MANIFESTO_MINUTOS em MANIFESTO_MINUTOS, pede o manifesto a cada sistema."""
    import asyncio
    from database import SessionLocal
    from nucleo import manifestos
    await asyncio.sleep(20)                 # deixa os sistemas subirem junto
    while True:
        db = SessionLocal()
        try:
            await asyncio.to_thread(manifestos.buscar_todos, db)
        except Exception:  # noqa: BLE001
            logging.getLogger("solobot").exception("Busca de manifestos falhou")
        finally:
            db.close()
        await asyncio.sleep(config.MANIFESTO_MINUTOS * 60)


async def _despachar_avisos_sempre():
    """A cada minuto, solta os avisos que esperavam o horário de silêncio acabar."""
    import asyncio
    from database import SessionLocal
    from nucleo import avisos
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            await asyncio.to_thread(avisos.despachar_pendentes, db)
        except Exception:  # noqa: BLE001
            logging.getLogger("solobot").exception("Despacho de avisos falhou")
        finally:
            db.close()


@asynccontextmanager
async def _vida(_app):
    import asyncio
    criar_tabelas()
    tarefas = []
    if config.MANIFESTO_MINUTOS > 0:
        tarefas.append(asyncio.create_task(_buscar_manifestos_sempre()))
    if not config.AMBIENTE == "test":
        tarefas.append(asyncio.create_task(_despachar_avisos_sempre()))
    yield
    for t in tarefas:
        t.cancel()


app = FastAPI(title="Solo Bot", lifespan=_vida, docs_url="/api/docs" if config.DEV else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def cabecalhos(request: Request, call_next):
    r = await call_next(request)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("Referrer-Policy", "same-origin")
    r.headers.setdefault("X-Frame-Options", "DENY")
    return r


for r in (auth.router, conta.router, conectar.router, webhooks.router, interno.router, admin.router):
    app.include_router(r)


@app.get("/saude")
def saude():
    return {"ok": True}


# ── Páginas ───────────────────────────────────────────────────────
PAGINAS = {"/": "index.html", "/entrar": "index.html", "/cadastro": "index.html",
           "/painel": "painel.html", "/conectar": "conectar.html", "/admin": "admin.html"}


def _pagina(nome: str):
    return lambda: FileResponse(FRONT / nome, headers={"Cache-Control": "no-cache"})


for rota, arquivo in PAGINAS.items():
    app.add_api_route(rota, _pagina(arquivo), include_in_schema=False)

app.mount("/static", StaticFiles(directory=FRONT / "static"), name="static")


@app.exception_handler(404)
async def _nao_achou(request: Request, exc):
    from fastapi.responses import JSONResponse
    if request.url.path.startswith(("/api", "/interno")):
        return JSONResponse({"detail": getattr(exc, "detail", "Não encontrado.")}, status_code=404)
    return RedirectResponse("/")
