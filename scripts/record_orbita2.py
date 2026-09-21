"""Grava a sequência da Estação Órbita-2 direto do motor do projeto.

Os GIFs que estão em docs/img/ do space-station-pygame são de antes do merge que
trouxe o Sistema Solar real, o interior da estação e os telescópios. Em vez de
rebaixá-los, este script roda o próprio `ap1.py` sem janela (SDL dummy, o mesmo
truque do docs/gerar_figuras.py de lá) e captura quadro a quadro, então a prévia
do README sempre mostra o estado atual do projeto.

O instante da simulação é fixo: a pose da estação depende do relógio UTC, e sem
fixar isso o GIF sairia diferente a cada execução.

Uso:
    python scripts/record_orbita2.py            # grava e grava assets/orbita2.gif
    python scripts/record_orbita2.py --update   # git pull antes de gravar
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / ".cache" / "space-station"
REPO = "https://github.com/gblsun/space-station-pygame.git"

# Mesmo instante que o projeto usa nas figuras da documentação
INSTANT = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
SIM_STEP = 1.0 / 60.0
OUTPUT_FPS = 10
WIDTH, HEIGHT = 560, 373

# Um enquadramento por fase, trocado no limite de cada uma. `go_to` faz a
# transição suave, então a troca aparece como um movimento de câmera.
CAMERA_PLAN = ("direita", "geral", "direita", "superior")


def ensure_checkout(update=False):
    if not CHECKOUT.exists():
        CHECKOUT.parent.mkdir(parents=True, exist_ok=True)
        print(f"  clonando {REPO}")
        subprocess.run(["git", "clone", "--depth", "1", "-q", REPO, str(CHECKOUT)], check=True)
    elif update:
        print("  atualizando o checkout")
        subprocess.run(["git", "-C", str(CHECKOUT), "pull", "-q", "--depth", "1"], check=True)
    return CHECKOUT


def load_engine(update=False):
    """Importa o ap1 sem abrir janela nem áudio."""
    ensure_checkout(update)
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, str(CHECKOUT / "Atividade AP1"))
    import pygame
    import ap1

    pygame.init()
    return pygame, ap1


def capture(update=False, width=WIDTH, height=HEIGHT, fps=OUTPUT_FPS):
    """Devolve (quadros PIL em RGB, durações em ms) da sequência completa."""
    from PIL import Image

    pygame, ap1 = load_engine(update)
    every = max(1, round((1.0 / fps) / SIM_STEP))

    scene = ap1.Scene(INSTANT)
    scene.state = ap1.STATE_EXECUTANDO
    frame = pygame.Surface((ap1.BASE_WIDTH, ap1.BASE_HEIGHT))
    renderer, hud = ap1.Renderer(), ap1.Hud()
    scene.camera.go_to(CAMERA_PLAN[0])

    frames, durations = [], []
    total = int(round(ap1.TOTAL_SEQUENCE_TIME / SIM_STEP))
    phase = 0
    for step in range(total):
        elapsed = step * SIM_STEP
        # troca de câmera ao entrar em cada fase
        while phase + 1 < len(ap1.PHASE_BOUNDS) and elapsed >= ap1.PHASE_BOUNDS[phase]:
            phase += 1
            scene.camera.go_to(CAMERA_PLAN[min(phase, len(CAMERA_PLAN) - 1)])
        scene.update(SIM_STEP)
        if step % every:
            continue
        renderer.draw(frame, scene)
        hud.draw(frame, scene, renderer)
        image = Image.frombytes("RGB", frame.get_size(), pygame.image.tobytes(frame, "RGB"))
        frames.append(image.resize((width, height), Image.LANCZOS))
        durations.append(round(every * SIM_STEP * 1000))

    print(f"  {len(frames)} quadros · {sum(durations) / 1000:.1f}s · {width}x{height}"
          f" (motor em {ap1.BASE_WIDTH}x{ap1.BASE_HEIGHT})")
    return frames, durations


def main():
    parser = argparse.ArgumentParser(description="Grava a sequência da Estação Órbita-2.")
    parser.add_argument("--update", action="store_true", help="git pull no checkout antes de gravar")
    args = parser.parse_args()

    import recolor_gifs

    recolor_gifs.build("orbita2.gif", recolor_gifs.SOURCES["orbita2.gif"], args.update)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
