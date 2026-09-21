"""Gera os widgets do perfil a partir da API GraphQL do GitHub.

Saídas (em --out): banner.svg, stats.svg, top-langs.svg, activity-graph.svg,
medium.svg e spotify.svg, publicadas no branch `output` pelo workflow.

Uso local:
    GITHUB_TOKEN=$(gh auth token) python scripts/profile_widgets.py --out dist

O card do Spotify só mostra dados com os três secrets abaixo; sem eles vira um
card fixo apontando para o perfil, e nunca uma imagem quebrada:
    SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET  do app em developer.spotify.com
    SPOTIFY_REFRESH_TOKEN                      de um code trocado no escopo
                                               user-top-read

Fora o Pillow (só para recortar a textura do banner), usa apenas a biblioteca
padrão. Com um token que enxerga repos privados, eles entram na soma de commits
e de linguagens (sem nomes).
"""

import argparse
import base64
import json
import math
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

USER = "gblsun"
GRAPH_DAYS = 31
# Notebooks com saídas embutidas e relatórios HTML exportados somam megabytes
# e escondem o código de verdade no card de linguagens
EXCLUDED_LANGUAGES = {"Jupyter Notebook", "HTML"}

# Mesma paleta hyperpop do README (assets/*.svg e os badges do shields.io)
BG = "#101521"
GRID = "#2B3950"
TEXT = "#E8EEF5"
MUTED = "#7C8CA5"
CYAN = "#58F7FF"
PINK = "#FF4FD8"
AMBER = "#FFC857"
# Ordenadas para que duas fatias vizinhas da barra nunca tenham a mesma
# luminância — quem não distingue as matizes ainda separa os blocos
LANG_COLORS = ["#58F7FF", "#FF4FD8", "#FFC857", "#8B7CFF", "#5BE9B9", "#FF8A73"]
OTHER_COLOR = "#39445C"
SANS = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
MONO = "Consolas, 'Fira Code', 'DejaVu Sans Mono', monospace"

QUERY = """
query ($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      nodes {
        isPrivate
        stargazerCount
        pushedAt
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    pullRequests { totalCount }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
  }
}
"""


def graphql(token, variables):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{USER}-profile-widgets",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise SystemExit(f"Erro na API GraphQL: {payload['errors']}")
    return payload["data"]["user"]


def fmt_number(value):
    return f"{value:,}".replace(",", ".")


def card(width, height, title, body, extra_style=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <defs>
    <linearGradient id="frame" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{PINK}"/>
      <stop offset="100%" stop-color="{CYAN}"/>
    </linearGradient>
  </defs>
  <style>
    .fade {{ opacity: 0; animation: fade .6s ease-out forwards; }}
    @keyframes fade {{ to {{ opacity: 1; }} }}{extra_style}
    /* Sem isto, quem desliga animação veria o card vazio: o conteúdo nasce em
       opacity 0 e só a animação o revela. */
    @media (prefers-reduced-motion: reduce) {{
      .fade {{ opacity: 1; animation: none; }}
      .ring, .draw {{ stroke-dashoffset: 0; animation: none; }}
    }}
  </style>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="14" fill="{BG}" stroke="url(#frame)" stroke-width="1.5"/>
  <text x="24" y="36" font-family="{SANS}" font-size="17" font-weight="600" fill="{CYAN}">{escape(title)}</text>
{body}
</svg>
"""


def stats_svg(user):
    collection = user["contributionsCollection"]
    public = [repo for repo in user["repositories"]["nodes"] if not repo["isPrivate"]]
    rows = [
        ("Commits no último ano", collection["totalCommitContributions"] + collection["restrictedContributionsCount"]),
        ("Estrelas recebidas", sum(repo["stargazerCount"] for repo in public)),
        ("Pull requests", user["pullRequests"]["totalCount"]),
        ("Repositórios públicos", len(public)),
        ("Contribuiu em outros repos", user["repositoriesContributedTo"]["totalCount"]),
    ]
    body = []
    for i, (label, value) in enumerate(rows):
        y = 72 + i * 24
        color = PINK if i % 2 == 0 else CYAN
        body.append(
            f'  <g class="fade" style="animation-delay: {0.15 * i:.2f}s">\n'
            f'    <circle cx="30" cy="{y - 5}" r="3.5" fill="{color}"/>\n'
            f'    <text x="44" y="{y}" font-family="{SANS}" font-size="14" fill="{TEXT}">{escape(label)}</text>\n'
            f'    <text x="310" y="{y}" font-family="{MONO}" font-size="15" font-weight="700" fill="{color}" text-anchor="end">{fmt_number(value)}</text>\n'
            f"  </g>"
        )

    total = collection["contributionCalendar"]["totalContributions"]
    circumference = 2 * math.pi * 52
    body.append(
        f'  <circle cx="405" cy="112" r="52" fill="none" stroke="{GRID}" stroke-width="7"/>\n'
        f'  <circle class="ring" cx="405" cy="112" r="52" fill="none" stroke="url(#frame)" stroke-width="7" stroke-linecap="round"'
        f' stroke-dasharray="{circumference:.1f}" transform="rotate(-90 405 112)"/>\n'
        f'  <text x="405" y="116" font-family="{MONO}" font-size="26" font-weight="700" fill="{TEXT}" text-anchor="middle">{fmt_number(total)}</text>\n'
        f'  <text x="405" y="136" font-family="{SANS}" font-size="11" fill="{MUTED}" text-anchor="middle">contribuições</text>\n'
        f'  <text x="405" y="180" font-family="{SANS}" font-size="11" fill="{MUTED}" text-anchor="middle">últimos 12 meses</text>'
    )
    ring_style = (
        f"\n    .ring {{ stroke-dashoffset: {circumference:.1f}; animation: ring 1.6s ease-out .3s forwards; }}"
        "\n    @keyframes ring { to { stroke-dashoffset: 0; } }"
    )
    return card(495, 195, "Estatísticas do GitHub", "\n".join(body), ring_style)


def top_langs_svg(user, limit=6):
    totals = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name not in EXCLUDED_LANGUAGES:
                totals[name] = totals.get(name, 0) + edge["size"]
    grand_total = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    items = [(name, size, LANG_COLORS[i]) for i, (name, size) in enumerate(ranked[:limit])]
    others = grand_total - sum(size for _, size, _ in items)
    if others > 0:
        items.append(("Outras", others, OTHER_COLOR))

    body = ['  <clipPath id="bar"><rect x="24" y="54" width="447" height="10" rx="5"/></clipPath>', '  <g clip-path="url(#bar)">']
    x = 24.0
    for name, size, color in items:
        width = 447 * size / grand_total
        body.append(f'    <rect x="{x:.2f}" y="54" width="{width + 0.5:.2f}" height="10" fill="{color}"/>')
        x += width
    body.append("  </g>")

    for i, (name, size, color) in enumerate(items):
        column, row = i % 2, i // 2
        left = 24 + column * 236
        y = 98 + row * 26
        percent = f"{100 * size / grand_total:.1f}%".replace(".", ",")
        body.append(
            f'  <g class="fade" style="animation-delay: {0.1 * i:.2f}s">\n'
            f'    <circle cx="{left + 5}" cy="{y - 5}" r="5" fill="{color}"/>\n'
            f'    <text x="{left + 18}" y="{y}" font-family="{SANS}" font-size="13.5" fill="{TEXT}">{escape(name)}</text>\n'
            f'    <text x="{left + 212}" y="{y}" font-family="{MONO}" font-size="13" fill="{MUTED}" text-anchor="end">{percent}</text>\n'
            f"  </g>"
        )
    return card(495, 195, "Linguagens mais usadas", "\n".join(body))


def activity_svg(user, days=GRAPH_DAYS):
    calendar = user["contributionsCollection"]["contributionCalendar"]
    series = [day for week in calendar["weeks"] for day in week["contributionDays"]][-days:]
    counts = [day["contributionCount"] for day in series]

    width, height = 900, 320
    left, right, top, bottom = 56, 872, 84, 268
    peak = max(counts)
    y_max = max(4, math.ceil(peak / 4) * 4)
    step_x = (right - left) / (len(series) - 1)

    def point(i, count):
        return left + i * step_x, bottom - (bottom - top) * count / y_max

    points = [point(i, count) for i, count in enumerate(counts)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points))
    area = f"{line} L{points[-1][0]:.1f},{bottom} L{points[0][0]:.1f},{bottom} Z"

    body = [
        '  <defs>',
        '    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">',
        f'      <stop offset="0%" stop-color="{CYAN}" stop-opacity="0.35"/>',
        f'      <stop offset="100%" stop-color="{CYAN}" stop-opacity="0"/>',
        '    </linearGradient>',
        '    <filter id="glow" x="-5%" y="-20%" width="110%" height="140%"><feGaussianBlur stdDeviation="3"/></filter>',
        '  </defs>',
    ]

    total = sum(counts)
    peak_day = series[counts.index(peak)]["date"]
    average = f"{total / len(counts):.1f}".replace(".", ",")
    subtitle = f"{fmt_number(total)} contribuições · média de {average} por dia · pico de {peak} em {peak_day[8:10]}/{peak_day[5:7]}"
    body.append(f'  <text x="24" y="60" font-family="{SANS}" font-size="13" fill="{MUTED}">{escape(subtitle)}</text>')

    for tick in range(5):
        value = y_max * tick // 4
        y = bottom - (bottom - top) * tick / 4
        body.append(f'  <line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{GRID}" stroke-opacity="0.6" stroke-width="1"/>')
        body.append(f'  <text x="{left - 12}" y="{y + 4:.1f}" font-family="{MONO}" font-size="11" fill="{MUTED}" text-anchor="end">{value}</text>')
    for i in range(0, len(series), 5):
        x = points[i][0]
        date = series[i]["date"]
        body.append(f'  <text x="{x:.1f}" y="{bottom + 22}" font-family="{MONO}" font-size="11" fill="{MUTED}" text-anchor="middle">{date[8:10]}/{date[5:7]}</text>')

    body.append(f'  <path class="fade" d="{area}" fill="url(#area)" style="animation-delay: .9s"/>')
    body.append(f'  <path class="draw" d="{line}" pathLength="1" fill="none" stroke="{PINK}" stroke-width="6" stroke-opacity="0.5" filter="url(#glow)"/>')
    body.append(f'  <path class="draw" d="{line}" pathLength="1" fill="none" stroke="{PINK}" stroke-width="2.5" stroke-linejoin="round"/>')
    for i, (x, y) in enumerate(points):
        color = AMBER if counts[i] == peak and peak > 0 else "#ffffff"
        body.append(f'  <circle class="fade" cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}" style="animation-delay: {1.2 + i * 0.02:.2f}s"/>')

    draw_style = (
        "\n    .draw { stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 1.8s ease-in-out forwards; }"
        "\n    @keyframes draw { to { stroke-dashoffset: 0; } }"
    )
    return card(width, height, f"Contribuições nos últimos {days} dias", "\n".join(body), draw_style)



BANNER_W, BANNER_H = 1200, 400
# A textura é desenhada mais larga que o quadro para o parallax ter para onde correr
TEXTURE_W = 1400
# O banner é a imagem de capa dos dois READMEs, então sai em duas línguas
ROLES = {
    "pt": ("Data & Analytics Intern @ PwC",
           "6º semestre de Ciência da Computação · Impacta",
           "Python · Java · Dados · Design"),
    "en": ("Data & Analytics Intern @ PwC",
           "6th semester of Computer Science · Impacta",
           "Python · Java · Data · Design"),
}
CHIP_LABELS = {
    "pt": ("contribuições", "repos públicos", "último commit"),
    "en": ("contributions", "public repos", "last commit"),
}

# CSS e não SMIL: assim `prefers-reduced-motion` consegue congelar tudo. Um SVG
# servido dentro de <img> executa animação declarativa, mas não scripts.
BANNER_STYLE = """
    .tex    { animation: pan 26s ease-in-out infinite alternate; }
    .sheen  { animation: sweep 6s linear infinite; }
    .rule   { animation: pulse 3.2s ease-in-out infinite; }
    .role   { opacity: 0; animation: role 13.5s infinite; }
    .chip   { opacity: 0; animation: rise .7s ease-out forwards; }
    @keyframes pan   { to { transform: translateX(-140px); } }
    @keyframes sweep { from { transform: translateX(-620px); } to { transform: translateX(620px); } }
    @keyframes pulse { 0%, 100% { opacity: .55; } 50% { opacity: 1; } }
    @keyframes role  { 0%, 1% { opacity: 0; } 5%, 28% { opacity: 1; } 33%, 100% { opacity: 0; } }
    @keyframes rise  { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) {
      .tex, .rule { animation: none; }
      .sheen { display: none; }
      .role { animation: none; opacity: 0; }
      .role-1 { opacity: 1; }
      .chip { animation: none; opacity: 1; }
    }
"""


def texture_uri(width, height, quality=74):
    """Recorta a textura cromada na proporção pedida e devolve um data URI.

    Vai embutida porque um SVG que o GitHub serve dentro de <img> não busca
    arquivo nenhum: um href relativo simplesmente não carregaria.
    """
    import base64
    import io

    from PIL import Image

    with Image.open(ROOT / "assets" / "hyperpop-background.jpg") as source:
        full_width, full_height = source.size
        band_height = round(full_width * height / width)
        top = max(0, (full_height - band_height) // 2)
        band = source.crop((0, top, full_width, min(full_height, top + band_height)))
        band = band.resize((width, height), Image.LANCZOS)
        buffer = io.BytesIO()
        band.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def relative_day(iso, lang="pt"):
    """'hoje' / 'today', 'ontem' / 'yesterday' ou a contagem de dias."""
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (datetime.now(timezone.utc) - moment).days
    if days <= 0:
        return "hoje" if lang == "pt" else "today"
    if days == 1:
        return "ontem" if lang == "pt" else "yesterday"
    return f"há {days} dias" if lang == "pt" else f"{days} days ago"


def banner_svg(user, lang="pt"):
    collection = user["contributionsCollection"]
    repos = user["repositories"]["nodes"]
    public = [repo for repo in repos if not repo["isPrivate"]]
    pushes = [repo["pushedAt"] for repo in repos if repo.get("pushedAt")]
    labels = CHIP_LABELS[lang]
    chips = [
        (fmt_number(collection["contributionCalendar"]["totalContributions"]), labels[0]),
        (fmt_number(len(public)), labels[1]),
        (relative_day(max(pushes), lang) if pushes else "—", labels[2]),
    ]

    # larguras estimadas pela métrica da monoespaçada, para centralizar a fileira
    widths = [round(7.05 * (len(value) + len(label) + 3)) + 34 for value, label in chips]
    total = sum(widths) + 14 * (len(chips) - 1)
    x = (BANNER_W - total) / 2
    pills = []
    for index, ((value, label), width) in enumerate(zip(chips, widths)):
        pills.append(
            f'    <g class="chip" style="animation-delay: {1.0 + index * 0.16:.2f}s">\n'
            f'      <rect x="{x:.0f}" y="314" width="{width}" height="34" rx="17" fill="{BG}" fill-opacity=".72" stroke="{GRID}"/>\n'
            f'      <text x="{x + 17:.0f}" y="336" font-family="{MONO}" font-size="13" font-weight="700" fill="{CYAN}">{escape(value)}</text>\n'
            f'      <text x="{x + 17 + 7.4 * (len(value) + 1):.0f}" y="336" font-family="{MONO}" font-size="13" fill="{MUTED}">{escape(label)}</text>\n'
            f"    </g>"
        )
        x += width + 14

    roles = "\n".join(
        f'    <text class="role role-{index + 1}" x="600" y="290" text-anchor="middle" font-family="{SANS}" font-size="17"'
        f' fill="{TEXT}" style="animation-delay: {-index * 4.5:.1f}s">{escape(role)}</text>'
        for index, role in enumerate(ROLES[lang])
    )

    pill_markup = "\n".join(pills)
    name = "GABRIEL PAVANELLI"
    name_attrs = (
        'x="600" y="192" text-anchor="middle" font-family="' + SANS + '" font-size="74"'
        ' font-weight="800" letter-spacing="6" textLength="880" lengthAdjust="spacingAndGlyphs"'
    )
    texture = texture_uri(TEXTURE_W, BANNER_H)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{BANNER_W}" height="{BANNER_H}" viewBox="0 0 {BANNER_W} {BANNER_H}" role="img" aria-label="Gabriel Pavanelli — GBLSUN, Digital Materials">
  <title>Gabriel Pavanelli — GBLSUN // DIGITAL MATERIALS</title>
  <defs>
    <linearGradient id="chrome" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffffff"/><stop offset="40%" stop-color="#cfdcee"/>
      <stop offset="52%" stop-color="#7a8aa3"/><stop offset="64%" stop-color="#f2f7ff"/>
      <stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
    <linearGradient id="glint" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{CYAN}" stop-opacity="0"/>
      <stop offset="42%" stop-color="{CYAN}"/><stop offset="58%" stop-color="{PINK}"/>
      <stop offset="100%" stop-color="{PINK}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="edge" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{BANNER_W}" y2="0">
      <stop offset="0%" stop-color="{CYAN}" stop-opacity="0"/><stop offset="22%" stop-color="{CYAN}"/>
      <stop offset="50%" stop-color="#f8fbff"/><stop offset="78%" stop-color="{PINK}"/>
      <stop offset="100%" stop-color="{PINK}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="veil" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{BG}" stop-opacity=".50"/>
      <stop offset="42%" stop-color="{BG}" stop-opacity=".58"/>
      <stop offset="100%" stop-color="{BG}" stop-opacity=".72"/>
    </linearGradient>
    <linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{BG}" stop-opacity="0"/>
      <stop offset="22%" stop-color="{BG}" stop-opacity=".62"/>
      <stop offset="78%" stop-color="{BG}" stop-opacity=".62"/>
      <stop offset="100%" stop-color="{BG}" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="frame"><rect width="{BANNER_W}" height="{BANNER_H}" rx="12"/></clipPath>
    <clipPath id="letters"><text {name_attrs}>{name}</text></clipPath>
  </defs>
  <style>{BANNER_STYLE}  </style>
  <g clip-path="url(#frame)">
    <image class="tex" href="{texture}" x="-140" y="0" width="{TEXTURE_W}" height="{BANNER_H}" preserveAspectRatio="xMidYMid slice"/>
    <rect width="{BANNER_W}" height="{BANNER_H}" fill="url(#veil)"/>
    <rect y="78" width="{BANNER_W}" height="300" fill="url(#scrim)"/>
    <path class="rule" d="M0 20 C210 6 350 38 560 22 S900 6 1200 24" fill="none" stroke="url(#edge)" stroke-width="3"/>

    <text {name_attrs} fill="url(#chrome)">{name}</text>
    <g clip-path="url(#letters)">
      <rect class="sheen" x="480" y="146" width="240" height="92" fill="url(#glint)" opacity=".9"/>
    </g>

    <path class="rule" d="M330 220 H870" stroke="url(#edge)" stroke-width="2.5" fill="none"/>
    <text x="600" y="250" text-anchor="middle" font-family="{MONO}" font-size="14" letter-spacing="6" fill="{CYAN}">GBLSUN // DIGITAL MATERIALS</text>

{roles}

{pill_markup}
    <path class="rule" d="M0 378 C210 364 350 396 560 380 S900 364 1200 382" fill="none" stroke="url(#edge)" stroke-width="2.5"/>
  </g>
</svg>
"""



MEDIUM_FEED = "https://medium.com/feed/@Gabriel.mp13"
SPOTIFY_PROFILE = "https://open.spotify.com/user/gabriel.mp13"
CARD_W = 760
MESES = ("jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez")


def wrap(text, limit):
    """Quebra em linhas de no máximo `limit` caracteres, sem cortar palavra."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fetch(url, headers=None, data=None):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def medium_posts(limit=3):
    """Últimos posts do feed do Medium. Devolve [] se o feed não responder."""
    try:
        raw = fetch(MEDIUM_FEED, {"User-Agent": f"{USER}-profile-widgets"})
    except Exception as error:                                  # feed fora do ar
        print(f"  medium: feed indisponível ({error})")
        return []
    namespace = {"content": "http://purl.org/rss/1.0/modules/content/"}
    posts = []
    for item in ET.fromstring(raw).findall(".//item")[:limit]:
        body = item.findtext("content:encoded", "", namespace)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        published = item.findtext("pubDate", "")
        try:
            moment = parsedate_to_datetime(published)
            date = f"{moment.day} {MESES[moment.month - 1]} {moment.year}"
        except (TypeError, ValueError):
            date = ""
        posts.append({
            "title": (item.findtext("title") or "").strip(),
            "date": date,
            "tags": [tag.text for tag in item.findall("category")][:3],
            "text": text,
        })
    return posts


def medium_svg():
    posts = medium_posts()
    if not posts:
        body = (f'  <text x="24" y="86" font-family="{SANS}" font-size="14" fill="{MUTED}">'
                "Nenhum post no feed agora.</text>")
        return card(CARD_W, 130, "Últimas publicações no Medium", body)

    rows, y = [], 78
    for index, post in enumerate(posts):
        color = PINK if index % 2 == 0 else CYAN
        title_lines = wrap(post["title"], 76)
        if len(title_lines) > 2:                       # corta com reticência, não no meio
            title_lines = title_lines[:2]
            title_lines[1] = title_lines[1].rstrip(" |-–—") + "…"
        rows.append(f'  <g class="fade" style="animation-delay: {0.12 * index:.2f}s">')
        rows.append(f'    <circle cx="31" cy="{y - 5}" r="4" fill="{color}"/>')
        for line_index, line in enumerate(title_lines):
            rows.append(
                f'    <text x="48" y="{y + line_index * 21}" font-family="{SANS}" font-size="15"'
                f' font-weight="600" fill="{TEXT}">{escape(line)}</text>'
            )
        meta = " · ".join(filter(None, [post["date"], *post["tags"]]))
        rows.append(
            f'    <text x="48" y="{y + len(title_lines) * 21 + 4}" font-family="{MONO}"'
            f' font-size="11.5" fill="{MUTED}">{escape(meta)}</text>'
        )
        rows.append("  </g>")
        y += len(title_lines) * 21 + 40
    return card(CARD_W, y + 6, "Últimas publicações no Medium", "\n".join(rows))


def spotify_top():
    """Faixas mais ouvidas. Precisa dos três secrets; sem eles devolve None."""
    client = os.environ.get("SPOTIFY_CLIENT_ID")
    secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    refresh = os.environ.get("SPOTIFY_REFRESH_TOKEN")
    if not (client and secret and refresh):
        return None
    try:
        basic = base64.b64encode(f"{client}:{secret}".encode()).decode()
        token = json.loads(fetch(
            "https://accounts.spotify.com/api/token",
            {"Authorization": f"Basic {basic}",
             "Content-Type": "application/x-www-form-urlencoded"},
            urllib.parse.urlencode({"grant_type": "refresh_token",
                                    "refresh_token": refresh}).encode(),
        ))["access_token"]
        payload = json.loads(fetch(
            "https://api.spotify.com/v1/me/top/tracks?limit=5&time_range=short_term",
            {"Authorization": f"Bearer {token}"},
        ))
    except Exception as error:
        print(f"  spotify: API indisponível ({error})")
        return None
    return [(item["name"], ", ".join(artist["name"] for artist in item["artists"]))
            for item in payload.get("items", [])]


def spotify_svg():
    tracks = spotify_top()
    if not tracks:
        # Sem os secrets o card não fica quebrado: vira um convite ao perfil.
        # Para ligar os dados, ver o cabeçalho deste arquivo.
        body = (
            f'  <text x="24" y="84" font-family="{SANS}" font-size="14" fill="{TEXT}">'
            "Hyperpop, glitch e eletrônica em rotação.</text>\n"
            f'  <text x="24" y="108" font-family="{SANS}" font-size="13" fill="{MUTED}">'
            f"{escape(SPOTIFY_PROFILE.replace('https://', ''))}</text>"
        )
        return card(CARD_W, 140, "No meu fone agora", body)

    rows = []
    for index, (name, artists) in enumerate(tracks):
        y = 80 + index * 30
        color = CYAN if index % 2 == 0 else PINK
        rows.append(
            f'  <g class="fade" style="animation-delay: {0.1 * index:.2f}s">\n'
            f'    <rect x="24" y="{y - 13}" width="4" height="16" rx="2" fill="{color}"/>\n'
            f'    <text x="40" y="{y}" font-family="{SANS}" font-size="14" fill="{TEXT}">'
            f"{escape(wrap(name, 44)[0])}</text>\n"
            f'    <text x="{CARD_W - 24}" y="{y}" font-family="{MONO}" font-size="12"'
            f' fill="{MUTED}" text-anchor="end">{escape(wrap(artists, 34)[0])}</text>\n'
            f"  </g>"
        )
    return card(CARD_W, 80 + len(tracks) * 30 + 22, "Mais ouvidas nas últimas 4 semanas",
                "\n".join(rows))


def main():
    parser = argparse.ArgumentParser(description="Gera os widgets SVG do perfil.")
    parser.add_argument("--out", type=Path, required=True, help="pasta onde os SVGs serão gravados")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("Defina GITHUB_TOKEN (localmente: GITHUB_TOKEN=$(gh auth token)).")

    user = graphql(token, {"login": USER})

    args.out.mkdir(parents=True, exist_ok=True)
    for name, svg in (
        ("banner.svg", banner_svg(user, "pt")),
        ("banner-en.svg", banner_svg(user, "en")),
        ("stats.svg", stats_svg(user)),
        ("top-langs.svg", top_langs_svg(user)),
        ("activity-graph.svg", activity_svg(user)),
        ("medium.svg", medium_svg()),
        ("spotify.svg", spotify_svg()),
    ):
        (args.out / name).write_text(svg, encoding="utf-8", newline="\n")
        print(f"{args.out / name}: gerado")


if __name__ == "__main__":
    main()
