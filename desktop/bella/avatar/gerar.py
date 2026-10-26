"""Processo local descartavel. Recebe somente foto e audio ja gerado."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import wave

# Ambientes Conda no Windows precisam dos seus DLLs sem alterar o PATH do usuario.
_dll_handles = []
if os.name == "nt":
    for pasta in (Path(sys.base_prefix), Path(sys.base_prefix) / "Library" / "bin"):
        if pasta.is_dir():
            _dll_handles.append(os.add_dll_directory(str(pasta)))


def fase(nome):
    print('AVATAR|' + nome, flush=True)


def executar(motor, foto, audio, destino):
    motor, foto, audio, destino = [Path(p).resolve() for p in (motor, foto, audio, destino)]
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg nao encontrado')
    wav = destino.parent / 'fala.wav'
    fase('audio')
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(audio),
                    '-t', '31', '-ar', '16000', '-ac', '1', str(wav)],
                   check=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    with wave.open(str(wav)) as w:
        duracao = w.getnframes() / w.getframerate()
    if duracao <= 0 or duracao > 30:
        fase('longa')
        return 3
    fase('modelo')
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA indisponivel')
    torch.set_num_threads(4)
    os.chdir(motor)
    sys.path.insert(0, str(motor))
    sys.argv = [str(motor / 'inference.py'), '--source_image', str(foto),
                '--driven_audio', str(wav), '--result_dir', str(destino.parent / 'saida'),
                '--size', '256', '--batch_size', '1', '--still']
    fase('geracao')
    runpy.run_path(str(motor / 'inference.py'), run_name='__main__')
    videos = list((destino.parent / 'saida').glob('*.mp4'))
    if len(videos) != 1 or videos[0].stat().st_size < 32:
        raise RuntimeError('Nenhum video valido')
    shutil.move(str(videos[0]), str(destino))
    fase('pronto')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for nome in ('motor', 'foto', 'audio', 'destino'):
        parser.add_argument('--' + nome, required=True)
    args = parser.parse_args()
    try:
        sys.exit(executar(args.motor, args.foto, args.audio, args.destino))
    except Exception:
        fase('falhou')  # Nunca devolver texto de conversa, caminhos ou excecoes brutas a UI.
        sys.exit(2)
