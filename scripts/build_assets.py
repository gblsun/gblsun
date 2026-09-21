"""Gera os assets estáticos do README: folhas de ícones e social preview.

Os glifos vêm do devicon (variantes `-plain`, de cor única) com fallback no
simple-icons, são repintados e assentados em tiles. Assim nada depende de um
serviço de terceiro em tempo de exibição e nenhum ícone chega em cor de marca.

O social preview é a imagem 1280x640 que o GitHub mostra quando alguém
compartilha o link do perfil. Ele não tem endpoint na API REST: depois de gerar,
subir em Settings > Social preview > Upload an image.

Uso:
    python scripts/build_assets.py
    python scripts/build_assets.py --refresh   # ignora o cache e rebaixa
"""

import argparse
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CACHE = ROOT / ".cache" / "icons"

DEVICON = "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/{}.svg"
SIMPLE = "https://cdn.jsdelivr.net/npm/simple-icons@13/icons/{}.svg"

TILE = 52
GLYPH = 30
GAP = 12
BG = "#1B2433"
BORDER = "#2B3950"
# Varredura ciano -> lilás -> magenta ao longo da fileira, ecoando os divisores
SWEEP = ((0x58, 0xF7, 0xFF), (0x8B, 0x7C, 0xFF), (0xFF, 0x4F, 0xD8))

# (rótulo, fonte, caminho no CDN)
ROWS = {
    "stack-linguagens.svg": [
        ("Python", DEVICON, "python/python-plain"),
        ("Java", DEVICON, "java/java-plain"),
        ("TypeScript", DEVICON, "typescript/typescript-plain"),
        ("JavaScript", DEVICON, "javascript/javascript-plain"),
        ("C++", DEVICON, "cplusplus/cplusplus-plain"),
        ("C", DEVICON, "c/c-original"),
        ("Elixir", DEVICON, "elixir/elixir-plain"),
        ("HTML5", DEVICON, "html5/html5-plain"),
        ("CSS3", DEVICON, "css3/css3-plain"),
        ("PowerShell", DEVICON, "powershell/powershell-plain"),
    ],
    "stack-ides.svg": [
        ("VS Code", DEVICON, "vscode/vscode-plain"),
        ("IntelliJ IDEA", DEVICON, "intellij/intellij-plain"),
        ("Eclipse", SIMPLE, "eclipseide"),
        ("PyCharm", DEVICON, "pycharm/pycharm-plain"),
        ("Visual Studio", DEVICON, "visualstudio/visualstudio-plain"),
        ("Android Studio", SIMPLE, "androidstudio"),
    ],
    "stack-sistemas.svg": [
        ("Arduino", DEVICON, "arduino/arduino-plain"),
        ("Debian", DEVICON, "debian/debian-plain"),
        ("Ubuntu", DEVICON, "ubuntu/ubuntu-plain"),
        ("Linux", DEVICON, "linux/linux-plain"),
        ("Windows", DEVICON, "windows11/windows11-original"),
        ("Kali Linux", SIMPLE, "kalilinux"),
        ("AWS", SIMPLE, "amazonwebservices"),
        ("Azure", DEVICON, "azure/azure-plain"),
        ("Google Cloud", DEVICON, "googlecloud/googlecloud-plain"),
        ("Git", DEVICON, "git/git-plain"),
        ("GitHub", DEVICON, "github/github-original"),
    ],
    "stack-dados.svg": [
        ("Next.js", SIMPLE, "nextdotjs"),
        ("Node.js", DEVICON, "nodejs/nodejs-plain"),
        ("SQLite", DEVICON, "sqlite/sqlite-plain"),
        ("scikit-learn", SIMPLE, "scikitlearn"),
    ],
}

# Cada ícone social tem link próprio, e região clicável dentro de um SVG servido
# como <img> não funciona — por isso cada um vira um arquivo.
SOCIAL = {
    "github": ("GitHub", SIMPLE, "github", "#58F7FF"),
    "linkedin": ("LinkedIn", SIMPLE, "linkedin", "#7BC6FF"),
    "spotify": ("Spotify", SIMPLE, "spotify", "#8B7CFF"),
    "discord": ("Discord", SIMPLE, "discord", "#C46BF0"),
    "gmail": ("E-mail", SIMPLE, "gmail", "#FF4FD8"),
}


def sweep_color(position):
    """Amostra a rampa ciano->lilás->magenta em `position` (0..1)."""
    scaled = position * (len(SWEEP) - 1)
    index = min(int(scaled), len(SWEEP) - 2)
    factor = scaled - index
    low, high = SWEEP[index], SWEEP[index + 1]
    return "#%02X%02X%02X" % tuple(
        round(low[c] + (high[c] - low[c]) * factor) for c in range(3)
    )


def download(template, path, refresh=False):
    target = CACHE / (path.replace("/", "__") + ".svg")
    if target.exists() and not refresh:
        return target.read_text(encoding="utf-8")
    CACHE.mkdir(parents=True, exist_ok=True)
    url = template.format(path)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            source = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{path}: {url} respondeu {error.code}. Corrija o slug.")
    target.write_text(source, encoding="utf-8")
    return source


def glyph(source, color, label):
    """Devolve (viewBox, conteúdo repintado) do SVG de origem."""
    match = re.search(r'viewBox="([^"]+)"', source)
    if not match:
        raise SystemExit("SVG de origem sem viewBox")
    view_box = match.group(1)
    body = source[source.index(">", source.index("<svg")) + 1:source.rindex("</svg>")]
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    # Um glifo que depende de gradiente ou de mais de uma cor para desenhar a
    # forma vira um bloco sólido quando é achatado numa cor só. Melhor falhar do
    # que publicar uma folha com um borrão: troque o slug por uma variante mono.
    if "url(#" in body:
        raise SystemExit(f"{label}: o SVG de origem usa gradiente. Use uma variante monocromática.")
    tones = {tone.lower() for tone in re.findall(r"#[0-9a-fA-F]{3,8}\b", body)}
    if len(tones) > 1:
        raise SystemExit(
            f"{label}: o SVG de origem tem {len(tones)} cores ({', '.join(sorted(tones))}). "
            "Use uma variante monocromática."
        )
    # fill="none" tem de sobreviver: só as cores literais são reescritas
    body = re.sub(r"#[0-9a-fA-F]{3,8}\b", color, body)
    return view_box, body.strip()


def sheet(icons, refresh=False):
    width = len(icons) * TILE + (len(icons) - 1) * GAP
    offset = (TILE - GLYPH) / 2
    parts = []
    for index, (label, template, path) in enumerate(icons):
        color = sweep_color(index / max(len(icons) - 1, 1))
        view_box, body = glyph(download(template, path, refresh), color, label)
        x = index * (TILE + GAP)
        parts.append(
            f'  <g><rect x="{x}" y="0" width="{TILE}" height="{TILE}" rx="13" fill="{BG}" stroke="{BORDER}"/>'
            f'<svg x="{x + offset:g}" y="{offset:g}" width="{GLYPH}" height="{GLYPH}" viewBox="{view_box}">'
            f'<g fill="{color}">{body}</g></svg></g>'
        )
    names = ", ".join(label for label, _, _ in icons)
    return (
        f'<svg viewBox="0 0 {width} {TILE}" width="{width}" height="{TILE}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{names}">\n'
        f"  <title>{names}</title>\n" + "\n".join(parts) + "\n</svg>\n"
    ), names


def social(key, spec, refresh=False):
    label, template, path, color = spec
    view_box, body = glyph(download(template, path, refresh), color, label)
    offset = (TILE - GLYPH) / 2
    return (
        f'<svg viewBox="0 0 {TILE} {TILE}" width="{TILE}" height="{TILE}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{label}">\n'
        f"  <title>{label}</title>\n"
        f'  <rect width="{TILE}" height="{TILE}" rx="14" fill="{BG}" stroke="{BORDER}"/>\n'
        f'  <svg x="{offset:g}" y="{offset:g}" width="{GLYPH}" height="{GLYPH}" viewBox="{view_box}">'
        f'<g fill="{color}">{body}</g></svg>\n</svg>\n'
    )



# O GitHub recorta a social preview para 1280x640
SOCIAL_PREVIEW = (1280, 640)
# O primeiro que existir na máquina; o arquivo é gerado uma vez e commitado,
# então não precisa das mesmas fontes em toda parte
FONTS = {
    "bold": ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    "mono": ("C:/Windows/Fonts/consola.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
             "/System/Library/Fonts/Menlo.ttc"),
    "sans": ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/System/Library/Fonts/Supplemental/Arial.ttf"),
}


def load_font(kind, size):
    from PIL import ImageFont

    for candidate in FONTS[kind]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit(f"Nenhuma fonte '{kind}' encontrada. Ajuste FONTS em {Path(__file__).name}.")


def centered(draw, text, font, y, fill, width, spacing=0):
    """Desenha `text` centralizado, com espaçamento opcional entre letras."""
    if not spacing:
        length = draw.textlength(text, font=font)
        draw.text(((width - length) / 2, y), text, font=font, fill=fill)
        return
    total = sum(draw.textlength(char, font=font) + spacing for char in text) - spacing
    x = (width - total) / 2
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + spacing


def social_preview():
    from PIL import Image, ImageDraw

    width, height = SOCIAL_PREVIEW
    with Image.open(ASSETS / "hyperpop-background.jpg") as source:
        full_w, full_h = source.size
        band_h = round(full_w * height / width)
        top = max(0, (full_h - band_h) // 2)
        art = source.crop((0, top, full_w, min(full_h, top + band_h)))
        art = art.resize((width, height), Image.LANCZOS).convert("RGB")

    # mesmo véu do banner, para as duas peças parecerem a mesma família
    veil = Image.new("RGB", (width, height), (0x10, 0x15, 0x21))
    art = Image.blend(art, veil, 0.62)
    draw = ImageDraw.Draw(art)

    centered(draw, "GABRIEL PAVANELLI", load_font("bold", 88), 236, "#F8FBFF", width, spacing=6)
    for offset, color in ((0, "#58F7FF"), (1, "#FF4FD8")):
        draw.line([(340, 356 + offset), (940, 356 + offset)], fill=color, width=1)
    centered(draw, "GBLSUN // DIGITAL MATERIALS", load_font("mono", 22), 386, "#58F7FF", width, spacing=6)
    centered(draw, "Data & Analytics Intern @ PwC  ·  Ciência da Computação",
             load_font("sans", 24), 438, "#E8EEF5", width)

    # JPEG e não PNG: a textura é fotográfica, e o GitHub recusa acima de 1 MB
    target = ASSETS / "social-preview.jpg"
    art.save(target, "JPEG", quality=88, optimize=True, progressive=True)
    print(f"assets/{target.name}: {width}x{height} · {target.stat().st_size / 1024:.0f} KB")
    print("    subir em Settings > Social preview > Upload an image")


def main():
    parser = argparse.ArgumentParser(description="Gera os assets estáticos do README.")
    parser.add_argument("--refresh", action="store_true", help="rebaixa os glifos de origem")
    args = parser.parse_args()

    for name, icons in ROWS.items():
        markup, names = sheet(icons, args.refresh)
        (ASSETS / name).write_text(markup, encoding="utf-8", newline="\n")
        print(f"assets/{name}: {len(icons)} ícones")
        print(f"    alt: {names}")

    folder = ASSETS / "social"
    folder.mkdir(exist_ok=True)
    for key, spec in SOCIAL.items():
        (folder / f"{key}.svg").write_text(social(key, spec, args.refresh), encoding="utf-8", newline="\n")
    print(f"assets/social/: {len(SOCIAL)} ícones")

    social_preview()


if __name__ == "__main__":
    main()
