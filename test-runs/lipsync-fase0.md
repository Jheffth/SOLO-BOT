# Solo Lipsync — Fase 0 (MuseTalk 1.5 na RTX 5060 Ti)

Data: 25/11/2026. Executado por Claude (Sonnet 5.5) neste PC. Nada foi integrado com a Bella.exe.

## Veredito

**Inconclusivo, no limite do critério (25 fps).** Instalação e geração funcionam, mas o benchmark foi feito com a GPU
**ocupada por outros programas** (nvidia-smi mostrou 82–99 % de uso e ~8 GB de VRAM em uso *depois* do teste terminar:
processos Python do ComfyUI/VoiceStudio). Resultado da geração pura (UNet + VAE decode), medianas:

| batch_size | rodadas (fps) | mediana |
|---|---|---|
| 4 | 8,2 / 26,3 / 26,1 | **26,1** |
| 8 | 28,3 / 21,3 / 17,7 | **21,3** |
| 16 | 4,0 / 25,6 / 25,3 | **25,3** |

- Pico isolado de 28,3 fps no batch 8 e variação enorme entre rodadas (4 a 28 fps) indicam disputa pela GPU, não o limite do hardware.
- Pipeline completo do `realtime_inference` (UNet + VAE + mistura com a máscara, sem salvar imagens): 18,3 fps (batch 4), 14,4 (batch 8), 14,6 (batch 16).
  A mistura (`get_image_blending`, CPU, uma thread) é o gargalo nesse modo: 704x1216 é pesado. Na fase 2 vale misturar só o recorte
  da boca/rosto, em resolução menor (a janela da Bella é pequena) ou em paralelo.
- **Pendente:** repetir o benchmark com ComfyUI e VoiceStudio fechados (comando abaixo) antes de decidir sobre a fase 1.

## Versões

| Item | Versão |
|---|---|
| Python | 3.10.22 (via `uv`, em `%APPDATA%\uv\python\...`, fora do PATH) |
| PyTorch | 2.11.0+cu128 (torchvision 0.26.0+cu128, torchaudio 2.11.0+cu128), CUDA do torch 12.8 |
| GPU | RTX 5060 Ti, capability (12, 0), matmul fp16 OK |
| Driver | NVIDIA 621.24 (CUDA UMD 13.5) |
| numpy | 1.26.4 (o requirements pedia 1.23.5) |
| mmcv / mmdet / mmpose | **Plano B usado.** `mmcv-lite 2.0.1`, mmdet 3.1.0 e mmpose 1.1.0 ficaram instalados, mas **não são usados** |
| face-alignment | 1.5.0 (2D-FAN + S3FD) |
| ffmpeg | build BtbN master (win64 gpl), local em `solo-lipsync\ffmpeg\bin` |
| MuseTalk | clone `--depth 1` de TMElyralab/MuseTalk, em 25/11/2026 |

## Onde ficou instalado (tudo em `C:\JEFFERSON\IA\solo-lipsync\`, fora do git)

| Caminho | Tamanho |
|---|---|
| `lipsync-env\` (venv) | 5,14 GB |
| `MuseTalk\` (código + `models\` 5,48 GB + `results\` 0,45 GB) | ~6 GB |
| `ffmpeg\` | 0,50 GB |
| `testes\` (benchmark, shim, áudio, resultados, zip do ffmpeg) | 0,19 GB |
| Python 3.10 do uv (`%APPDATA%\uv\python`) | ~0,1 GB |
| Cache torch hub (`~\.cache\torch\hub\checkpoints`: 2DFAN4 e s3fd) | 0,19 GB |

Download total de pesos: ~6 GB (abaixo do limite de 10 GB). O `musetalk` v1.0 (3,4 GB) **não** foi baixado: só a v1.5.
Pesos conferidos (todos > 0 bytes): `musetalkV15/unet.pth` (3,40 GB) + `musetalk.json`, `sd-vae/` (335 MB), `whisper/` (151 MB),
`dwpose/dw-ll_ucoco_384.pth` (407 MB, baixado mas não usado no plano B), `face-parse-bisent/` (79999_iter.pth + resnet18), `syncnet/latentsync_syncnet.pt` (1,49 GB).

## Comandos que funcionaram, na ordem

```powershell
# 0. pasta e Python 3.10 (uv já estava instalado)
New-Item -ItemType Directory -Force C:\JEFFERSON\IA\solo-lipsync\testes
cd C:\JEFFERSON\IA\solo-lipsync
uv python install 3.10
# ffmpeg local (sem PATH global)
curl.exe -L -o testes\ffmpeg.zip https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip
Expand-Archive testes\ffmpeg.zip -DestinationPath ffmpeg-tmp; Move-Item (Get-ChildItem ffmpeg-tmp -Directory)[0].FullName ffmpeg; Remove-Item ffmpeg-tmp -Recurse

# 1. venv + pip/setuptools/wheel
uv venv lipsync-env --python 3.10
$py = 'C:\JEFFERSON\IA\solo-lipsync\lipsync-env\Scripts\python.exe'
uv pip install --python $py -U pip setuptools wheel

# 2. PyTorch Blackwell
uv pip install --python $py torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# 3. MuseTalk + requirements filtrado (sem torch*, tensorflow, tensorboard; numpy==1.26.4)
git clone --depth 1 https://github.com/TMElyralab/MuseTalk MuseTalk
#   testes\requirements-filtrado.txt = requirements.txt sem essas linhas
uv pip install --python $py -r testes\requirements-filtrado.txt
uv pip install --python $py face-alignment

# 4. pesos (huggingface_hub.snapshot_download, dentro de MuseTalk\)
#   TMElyralab/MuseTalk  -> models\ (so musetalkV15/*)
#   stabilityai/sd-vae-ft-mse -> models\sd-vae (config.json, diffusion_pytorch_model.bin)
#   openai/whisper-tiny -> models\whisper (config.json, pytorch_model.bin, preprocessor_config.json)
#   yzd-v/DWPose -> models\dwpose (dw-ll_ucoco_384.pth)
#   ByteDance/LatentSync -> models\syncnet (latentsync_syncnet.pt)
#   ManyOtherFunctions/face-parse-bisent -> models\face-parse-bisent (79999_iter.pth, resnet18-5c106cde.pth)

# 5. inferência normal v1.5 (com plano B), dentro de MuseTalk\
$env:PYTHONUTF8 = '1'; $env:PATH = 'C:\JEFFERSON\IA\solo-lipsync\ffmpeg\bin;' + $env:PATH
& $py ..\testes\run_planb.py scripts.inference --inference_config configs/inference/test.yaml --result_dir results/test `
  --unet_model_path models/musetalkV15/unet.pth --unet_config models/musetalkV15/musetalk.json --version v15

# 6. benchmark (clip de 10 s = primeiros 10 s de data\audio\eng.wav a 16 kHz mono)
..\ffmpeg\bin\ffmpeg.exe -y -i data\audio\eng.wav -t 10 -ar 16000 -ac 1 ..\testes\audio10s.wav
& $py ..\testes\benchmark.py --video data\video\yongen.mp4 --audio ..\testes\audio10s.wav --nome yongen
```

Arquivos de apoio em `C:\JEFFERSON\IA\solo-lipsync\testes\`: `benchmark.py`, `mmpose_shim.py` (plano B), `run_planb.py`,
`requirements-filtrado.txt`, `resultado-yongen.json`, `benchmark-yongen.log`, `frames-yongen.png`.

## Plano B (mmpose → face_alignment)

- **Problema:** não há wheel de `mmcv` com ops para torch 2.11/cu128 (o índice do openmmlab vai só até cu121/torch2.4; `mim install` exigiria
  compilar com Build Tools). O `mmcv-lite` instala e deixa `import mmpose` passar, mas `init_model` falha: `No module named 'mmcv._ext'`
  (mmdet importa `mmcv.ops.nms`).
- **Solução (aprovada pelo Jefferson):** `testes\mmpose_shim.py` injeta `mmpose.apis` / `mmpose.structures` falsos que usam `face_alignment`
  (2D-FAN, 68 pontos iBUG) e preenchem `keypoints[0][23:91]`, exatamente os índices que o MuseTalk lê. **Nenhum arquivo do repositório MuseTalk foi editado.**
  Afeta só o preparo do avatar. O README do plano dizia que o MuseTalk "já usa" face_alignment: na verdade ele só usa o detector S3FD
  (cópia própria em `musetalk\utils\face_detection`), então `face-alignment` foi instalado à parte.
- **Efeitos de segurança no shim:** `torch.load` com `weights_only=False` (os pesos da face-parsing estão no formato antigo e o torch ≥ 2.6 recusa);
  `TORCHDYNAMO_DISABLE=1` (sem triton no Windows, o `face_alignment` 1.5 tenta `torch.compile`). Pesos vêm dos repositórios oficiais; uso local.
- **Não validado:** a diferença de bbox entre dwpose e face_alignment. A caixa da boca nos quadros de teste ficou coerente, mas não há comparação lado a lado com dwpose.

## Resultados detalhados (yongen.mp4, 704x1216, 268 quadros; áudio de 10 s = 250 quadros)

| Medida | Valor |
|---|---|
| Carga dos modelos | 8,4 s |
| Preparo do avatar (landmarks + latentes + máscaras de 268 x 2 quadros) | 242,6 s (uma vez; só os landmarks levaram ~76 s no teste anterior) |
| Features do whisper para 10 s | 2,85 s |
| Geração pura, mediana: batch 4 / 8 / 16 | 26,1 / 21,3 / 25,3 fps |
| Pipeline com mistura, mediana: batch 4 / 8 / 16 | 18,3 / 14,4 / 14,6 fps |
| VRAM máxima alocada pelo torch (batch 4 / 8 / 16) | 6,0 / 3,3 / 7,0 GB (valores incoerentes entre si; medição contaminada, ver abaixo) |
| VRAM pico no nvidia-smi (sistema inteiro) | 15,7 GB de 16 GB (inclui os outros programas) |

Inferência normal (`scripts.inference`): `yongen_yongen.mp4` (8 s) e `yongen_eng.mp4` (60 s) gerados, h264 + aac, 704x1216, duração igual à do áudio.
60 s de áudio (1500 quadros) levaram ~157 s com a GPU compartilhada. Verificação da boca: só conferi 4 quadros parados
(`frames-yongen.png`: a boca muda de abertura entre eles); **não assisti ao vídeo**, então a sincronia precisa de olho humano.

## Problemas e soluções

1. Python 3.10 e ffmpeg ausentes → `uv python install 3.10` e zip estático local (autorizado).
2. Sem wheel mmcv cu128 → plano B (acima).
3. `torch.load` do torch ≥ 2.6 recusando pesos antigos → `weights_only=False` no shim.
4. `face_alignment` 1.5 exige triton → `TORCHDYNAMO_DISABLE=1`.
5. Erro de codificação (`charmap`) ao imprimir caracteres chineses no console → `PYTHONUTF8=1`.
6. `realtime_inference.py` tem o `--unet_model_path` padrão da v1.0: passar os caminhos da v1.5 (o `benchmark.py` já faz).
7. O primeiro `run` de cada batch tem aquecimento; o benchmark faz um aquecimento antes (batch 8).
8. Usei `uv pip` em vez de `pip` no venv (mesmo resultado, bem mais rápido).

## Pendências

- **Rodar de novo o benchmark com a GPU livre** (fechar ComfyUI e VoiceStudio) e confirmar o critério de 25 fps. Mesmo comando do passo 6.
- Passo 9 **pulado**: não existe `testes\bella-base.mp4` (é a fase 1).
- Assistir ao MP4 gerado e comparar o bbox do plano B com o dwpose, se possível.
- Otimizar a mistura (CPU) para o modo em fluxo da fase 4.
- Licenças (whisper, dwpose, face-parsing, VAE) antes de uso comercial; não verificadas aqui.
