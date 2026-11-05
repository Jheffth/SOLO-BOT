# Ponte da TV LG (webOS)

A Bella e o bot rodam na VPS; as TVs ficam em casa. A **ponte** roda no notebook, na mesma
rede das TVs, e faz **só conexões de saída** para o bot. Nenhuma porta do roteador é aberta.

```
Telegram / WhatsApp / Bella.exe ─► Solo Bot (VPS) ◄── long-poll HTTPS ── ponte.py (notebook) ─► TV LG
                                   nucleo/tv_lg.py      Bearer PONTE_TV_TOKEN      lgtv.py      ws://IP:3001
```

## Arquivos

| Arquivo | O que faz |
|---|---|
| `lgtv.py` | Fala com a TV (bscpylgtv), Wake-on-LAN, lista de ações permitidas, erros claros |
| `tv.py` | Linha de comando: parear, listar, gerar token, testar comandos |
| `ponte.py` | O serviço: busca comandos no bot, valida, executa e devolve o resultado |
| `tv_config.json` | **Fora do Git.** TVs, client-keys e token da ponte |
| `ponte.log` | **Fora do Git.** Registro de cada comando (gira em 1 MB) |

## Instalar e parear (uma vez)

```bash
pip install -r requirements.txt
python ../tools/descobrir_lg.py                        # acha IP das TVs
python tv.py parear sala 192.168.1.13 f0:86:20:f2:26:1e 50UN8000PSD
python tv.py parear quarto <ip> <mac>                  # outra TV, outro apelido
python tv.py lista
```

O pareamento mostra um pedido na TV; aceite com o controle em até 90 s. Reserve o IP de cada TV
no roteador (DHCP fixo) para ele não mudar. Para **ligar** pela rede, ative na TV
*Configurações → Geral → Dispositivos → Ligar via Wi-Fi* (ou *Mobile TV On*).

## Testar sem o bot

```bash
python tv.py sala estado
python tv.py sala aviso "Oi da Bella"
python tv.py sala volume definir 15      # subir · descer · mudo · som · definir N
python tv.py sala abrir_app netflix      # youtube · netflix · globoplay · prime
python tv.py sala entrada 2              # HDMI 1–4
python tv.py sala pause                  # play · pause · desligar · ligar
```

## Ligar a ponte ao bot

1. `python tv.py token https://solobot.duckdns.org` — gera o token e guarda em `tv_config.json`.
2. Na VPS, ponha a linha `PONTE_TV_TOKEN=…` que ele mostrou no `.env` do Solo Bot e reinicie
   (`docker compose up -d`). Sem o token, as rotas `/api/ponte-tv/*` nem existem.
3. No notebook: `python ponte.py` (ou `iniciar_ponte.bat`; atalho em `shell:startup` para subir com o Windows).

## Segurança

- Só saída: a ponte chama `GET /api/ponte-tv/proximo` (espera até 25 s) e `POST /api/ponte-tv/resultado`.
- Token secreto em `Authorization: Bearer`, comparado em tempo constante; exige `https://` (exceto localhost).
- Lista fechada de ações e valores, conferida no bot **e** na ponte (`ligar, desligar, volume, abrir_app,
  entrada, aviso, play, pause, estado` e os favoritos). Nada de comando livre; favorito só aceita
  link da Netflix ou do YouTube.
- Comando não buscado em 30 s é descartado: a TV não liga horas depois porque o notebook acordou.
- No bot, só a conta administradora comanda a TV.

## Favoritos (Netflix e YouTube)

Um favorito guarda só o **código** do título (Netflix) ou do vídeo (YouTube), em `tv_config.json`,
e vale para todas as TVs. Ao abrir, o app já vai para o título.

```text
/tv favorito The Chosen https://www.netflix.com/watch/81622759   guarda (aceita /watch/ e /title/)
abre The Chosen na tv  ·  abra a netflix em The Chosen             abre
/tv favoritos  ·  /tv esquecer The Chosen                         lista · tira
python tv.py sala favorito_salvar The Chosen <link>               o mesmo, sem o bot
```

Perfis e controle de maturidade continuam com a Netflix: se ela pedir o perfil, escolha no
controle. A ponte nunca escolhe perfil nem digita PIN (um perfil infantil continua protegido).
O YouTube abre o vídeo por `contentTarget`; isso ainda não foi testado nesta TV.

## Pelo bot

`/tv` mostra o estado da ponte e exemplos. Frases curtas que citam a TV viram comando:
“desliga a tv”, “liga a tv do quarto”, “volume 15 na tv”, “tv no mudo”, “abre o netflix na tv”,
“tv hdmi 2”, “pausa a tv”, “/tv aviso O jantar está pronto”.
Ações para o agente: `tv.ligar`, `tv.desligar`, `tv.volume`, `tv.abrir_app`, `tv.entrada`,
`tv.aviso`, `tv.play`, `tv.pause`, `tv.estado`, `tv.favorito_abrir`, `tv.favorito_salvar`,
`tv.favoritos`, `tv.favorito_apagar` (em `backend/nucleo/tv_lg.py`, `tv_lg.executar`).
