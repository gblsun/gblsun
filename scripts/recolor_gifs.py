"""Gera os GIFs do README aplicando o grade hyperpop nas capturas originais.

As capturas vêm dos repositórios públicos de origem (ver SOURCES), são baixadas
para um cache local e regravadas em assets/. Nada é editado no lugar: rodar o
script duas vezes produz exatamente o mesmo resultado.

Uso:
    python scripts/recolor_gifs.py             # regera todos
    python scripts/recolor_gifs.py orbita2     # regera só um
    python scripts/recolor_gifs.py --refresh   # ignora o cache e baixa de novo
"""

import argparse
import shutil
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CACHE = ROOT / ".cache" / "gifs"

STATION = "https://raw.githubusercontent.com/gblsun/space-station-pygame/main/docs/img/"
PROFILE = "https://raw.githubusercontent.com/gblsun/gblsun/main/assets/"

# `mix` é o quanto do gradient map hyperpop entra sobre a captura original.
# Capturas que já nascem na paleta levam um toque leve; a preview do tema
# Midnight Synthwave fica intacta (mix 0), senão a prévia mentiria sobre as
# cores que o tema realmente pinta no terminal.
SOURCES = {
    # Gravado do motor, não baixado: os GIFs em docs/img/ do projeto são
    # anteriores ao Sistema Solar real e ao interior da estação. Ver
    # scripts/record_orbita2.py.
    "orbita2.gif": {"mix": 0.42, "recorder": True, "colors": 160},
    # O cubo ocupa uma fração do quadro; o recorte aproxima a cena
    "knowledge-repo.gif": {
        "mix": 0.30,
        "parts": [PROFILE + "knowledge-repo.gif"],
        "crop": (0.0, 0.0, 0.78, 0.83),
    },
    "ordenacao-eficiente.gif": {"mix": 0.22, "parts": [PROFILE + "ordenacao-eficiente.gif"]},
    "midnight-synthwave.gif": {"mix": 0.00, "parts": [PROFILE + "midnight-synthwave.gif"]},
}

# Escuro profundo -> azul-tinta -> violeta -> lilás -> magenta -> ciano -> cromado
RAMP = [
    (0.00, (0x08, 0x0B, 0x12)),
    (0.20, (0x0F, 0x1E, 0x3C)),
    (0.40, (0x2A, 0x26, 0x68)),
    (0.58, (0x7A, 0x5C, 0xD8)),
    (0.74, (0xFF, 0x4F, 0xD8)),
    (0.88, (0x58, 0xF7, 0xFF)),
    (1.00, (0xFF, 0xFF, 0xFF)),
]


def _ramp_channels():
    ramp = []
    for value in range(256):
        position = value / 255
        for (start, low), (end, high) in zip(RAMP, RAMP[1:]):
            if start <= position <= end:
                factor = (position - start) / (end - start)
                ramp.append(tuple(round(low[c] + (high[c] - low[c]) * factor) for c in range(3)))
                break
    return [bytes(color[c] for color in ramp) for c in range(3)]


CHANNELS = _ramp_channels()
# Empurra os tons médios para baixo para o fundo não lavar sob o gradient map
GAMMA = bytes(round(255 * (value / 255) ** 1.18) for value in range(256))


def grade(frame, mix, saturation=1.75, contrast=1.16):
    """Mapeia a luminância na rampa hyperpop, preservando o contraste do original."""
    rgb = frame.convert("RGB")
    if not mix:
        return rgb
    luminance = rgb.convert("L").point(GAMMA)
    mapped = Image.merge("RGB", tuple(luminance.point(channel) for channel in CHANNELS))
    vivid = ImageEnhance.Color(rgb).enhance(saturation)
    return ImageEnhance.Contrast(Image.blend(vivid, mapped, mix)).enhance(contrast)


def download(url, refresh=False):
    target = CACHE / url.rsplit("/", 1)[-1]
    if target.exists() and not refresh:
        return target
    CACHE.mkdir(parents=True, exist_ok=True)
    print(f"  baixando {url}")
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out)
    return target


def read_frames(path, mix, crop=None):
    frames, durations = [], []
    with Image.open(path) as source:
        width, height = source.size
        box = None
        if crop:
            left, top, right, bottom = crop
            box = (round(left * width), round(top * height),
                   round(right * width), round(bottom * height))
        for index in range(source.n_frames):
            source.seek(index)
            frame = source.convert("RGB")
            if box:
                frame = frame.crop(box)
            frames.append(grade(frame, mix))
            durations.append(source.info.get("duration", 80))
    return frames, durations


def global_palette(frames, colors=255):
    """Uma paleta só para todos os quadros: sem ela o GIF engorda várias vezes."""
    sample = frames[:: max(1, len(frames) // 12)][:12]
    width, height = sample[0].size
    sheet = Image.new("RGB", (width, height * len(sample)))
    for index, frame in enumerate(sample):
        sheet.paste(frame, (0, index * height))
    return sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


def write_gif(frames, durations, target, colors=255):
    palette = global_palette(frames, colors)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    quantized[0].save(
        target,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        # optimize recorta cada quadro na região que mudou; sem ele o arquivo
        # fica ~7x maior, que foi como orbita2.gif chegou a 12,9 MB
        optimize=True,
    )


def build(name, spec, refresh=False):
    print(f"{name}:")
    frames, durations = [], []
    if spec.get("recorder"):
        # import tardio: o gravador importa este módulo de volta
        import record_orbita2

        captured, durations = record_orbita2.capture(update=refresh)
        frames = [grade(frame, spec["mix"]) for frame in captured]
    for url in spec.get("parts", ()):
        part_frames, part_durations = read_frames(
            download(url, refresh), spec["mix"], spec.get("crop")
        )
        frames += part_frames
        durations += part_durations
    target = ASSETS / name
    write_gif(frames, durations, target, spec.get("colors", 255))
    size = target.stat().st_size / 1e6
    print(f"  {len(frames)} quadros · {sum(durations) / 1000:.1f}s · {size:.2f} MB")


def main():
    parser = argparse.ArgumentParser(description="Regera os GIFs do README.")
    parser.add_argument("names", nargs="*", help="nomes a regerar (sem .gif); vazio = todos")
    parser.add_argument("--refresh", action="store_true", help="rebaixa as capturas de origem")
    args = parser.parse_args()

    wanted = {f"{name.removesuffix('.gif')}.gif" for name in args.names} or set(SOURCES)
    unknown = wanted - set(SOURCES)
    if unknown:
        raise SystemExit(f"Não conheço: {', '.join(sorted(unknown))}")

    for name in SOURCES:
        if name in wanted:
            build(name, SOURCES[name], args.refresh)


if __name__ == "__main__":
    main()
