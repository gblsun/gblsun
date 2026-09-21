"""Confere o README antes de publicar.

Cada checagem aqui existe porque o defeito correspondente já apareceu neste
repositório e só foi descoberto olhando a página renderizada:

  empilhamento  o GFM trata uma linha que não seja exatamente uma tag como
                parágrafo, e aí cada quebra vira <br>: fileiras de badges que
                deviam ficar lado a lado descem uma embaixo da outra.
  href externo  um SVG que o GitHub serve dentro de <img> não busca arquivo
                nenhum, então <image href="fundo.jpg"> nunca carrega.
  nasce oculto  conteúdo em opacity 0 revelado só por animação some inteiro
                para quem desliga movimento ou captura a imagem cedo.

Uso:
    python scripts/check_readme.py            # só o que está quebrado
    python scripts/check_readme.py --tudo     # inclui os avisos de peso
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
READMES = ("README.md", "README.en.md")

# acima disso o GitHub fica lento para servir e o perfil pesa em conexão ruim
SIZE_WARN_KB = {".gif": 2600, ".svg": 250, ".jpg": 400, ".png": 400}

# Um trecho de HTML no meio do markdown só fica cru (sem <br> nas quebras) se a
# PRIMEIRA linha abrir um bloco HTML: ou uma das tags de bloco do CommonMark
# (<table>, <div>, <p>…), ou uma linha que seja exatamente uma tag completa.
# Começar por <a> ou <img> com mais coisa na linha não abre bloco nenhum: vira
# parágrafo, e aí cada quebra de linha vira <br>.
BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|"
    "details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|"
    "h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|"
    "optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|"
    "tr|track|ul"
)
OPENS_BLOCK = re.compile(rf"^</?({BLOCK_TAGS})\b", re.I)
TAG_ONLY = re.compile(r"^<[a-zA-Z][^<>]*>$")

problems, warnings = [], []


def fail(where, message):
    problems.append(f"{where}: {message}")


def warn(where, message):
    warnings.append(f"{where}: {message}")


def check_references():
    """Todo asset citado existe, e todo asset existente é citado."""
    cited = set()
    for name in READMES:
        text = (ROOT / name).read_text(encoding="utf-8")
        for path in re.findall(r'src="(assets/[^"]+)"', text):
            cited.add(path)
            if not (ROOT / path).exists():
                fail(name, f"aponta para {path}, que não existe")

    # assets citados por outros assets (o rodapé embute a própria textura)
    for svg in ASSETS.rglob("*.svg"):
        for path in re.findall(r'href="(?!data:|https?:)([^"]+)"', svg.read_text(encoding="utf-8")):
            cited.add(f"assets/{path}")

    on_disk = {
        f"assets/{path.relative_to(ASSETS).as_posix()}"
        for path in ASSETS.rglob("*")
        if path.is_file()
    }
    # a textura alimenta o banner e o social preview por código, não por citação
    generated_from = {"assets/hyperpop-background.jpg", "assets/social-preview.jpg"}
    for orphan in sorted(on_disk - cited - generated_from):
        warn("assets", f"{orphan} não é citado por nenhum README")


def check_stacking():
    """Fileiras que o GFM vai quebrar com <br> em vez de deixar lado a lado."""
    for name in READMES:
        lines = (ROOT / name).read_text(encoding="utf-8").split("\n")
        run, start = [], 0
        for number, line in enumerate(lines + [""], 1):
            stripped = line.strip()
            if stripped.startswith("<") and not stripped.startswith("<!--"):
                if not run:
                    start = number
                run.append(stripped)
                continue
            if len(run) > 1 and not (OPENS_BLOCK.match(run[0]) or TAG_ONLY.match(run[0])):
                fail(name, f"linhas {start}-{start + len(run) - 1} viram parágrafo: "
                           f"o GFM insere <br> entre elas e a fileira empilha")
            run = []


def check_external_refs():
    """SVG servido como imagem não carrega recurso externo."""
    for svg in ASSETS.rglob("*.svg"):
        for href in re.findall(r'<image[^>]*href="([^"]+)"', svg.read_text(encoding="utf-8")):
            if not href.startswith("data:"):
                fail(svg.name, f'<image href="{href[:40]}"> não vai carregar dentro de <img>; '
                               "embuta em base64")


def check_hidden_content():
    """Conteúdo que só existe se a animação rodar."""
    for svg in ASSETS.rglob("*.svg"):
        text = svg.read_text(encoding="utf-8")
        hidden = len(re.findall(r'(?<!stop-)opacity="0"', text))
        dashed = len(re.findall(r'stroke-dashoffset="(?!0")', text))
        animated = "<animate" in text or "animation:" in text
        if not (hidden or dashed) or not animated:
            continue
        if "prefers-reduced-motion" not in text:
            fail(svg.name, f"{hidden + dashed} elemento(s) nascem ocultos e só a animação "
                           "os mostra, sem alternativa para movimento reduzido")


def check_alt_text():
    for name in READMES:
        text = (ROOT / name).read_text(encoding="utf-8")
        for tag in re.findall(r"<img\b[^>]*>", text):
            if 'alt=""' in tag:                      # decorativo, proposital
                continue
            if "alt=" not in tag:
                source = re.search(r'src="([^"]{0,60})', tag)
                fail(name, f"<img> sem alt: {source.group(1) if source else tag[:50]}")


def check_sizes():
    for path in sorted(ASSETS.rglob("*")):
        if not path.is_file():
            continue
        limit = SIZE_WARN_KB.get(path.suffix.lower())
        size = path.stat().st_size / 1024
        if limit and size > limit:
            warn("peso", f"{path.name} tem {size:.0f} KB (limite sugerido {limit} KB)")


def main():
    parser = argparse.ArgumentParser(description="Confere o README antes de publicar.")
    parser.add_argument("--tudo", action="store_true", help="mostra também os avisos")
    args = parser.parse_args()

    for check in (check_references, check_stacking, check_external_refs,
                  check_hidden_content, check_alt_text, check_sizes):
        check()

    for message in problems:
        print(f"  ERRO   {message}")
    if args.tudo or not problems:
        for message in warnings:
            print(f"  aviso  {message}")

    if problems:
        print(f"\n{len(problems)} problema(s).")
        return 1
    print(f"\nTudo certo. {len(warnings)} aviso(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
