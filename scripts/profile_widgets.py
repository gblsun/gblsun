"""Gera os widgets do perfil a partir da API GraphQL do GitHub.

Saídas (em --out): stats.svg, top-langs.svg e activity-graph.svg, publicadas
no branch `output` pelo workflow.

Uso local:
    GITHUB_TOKEN=$(gh auth token) python scripts/profile_widgets.py --out dist

Só usa a biblioteca padrão. Com um token que enxerga repos privados, eles
entram na soma de commits e de linguagens (sem nomes).
"""

import argparse
import json
import math
import os
import urllib.request
from html import escape
from pathlib import Path

USER = "gblsun"
GRAPH_DAYS = 31
# Notebooks com saídas embutidas e relatórios HTML exportados somam megabytes
# e escondem o código de verdade no card de linguagens
EXCLUDED_LANGUAGES = {"Jupyter Notebook", "HTML"}

# Mesma paleta do README (terminal-about.svg e co2-preview.svg)
BG = "#150a1f"
GRID = "#430d3c"
TEXT = "#e7dff0"
MUTED = "#8b7d96"
CYAN = "#00e5ff"
PINK = "#e5289e"
ORANGE = "#ef8539"
LANG_COLORS = ["#e5289e", "#00e5ff", "#ef8539", "#b967ff", "#fede5d", "#36f9a0"]
OTHER_COLOR = "#4b3d66"
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
        color = ORANGE if counts[i] == peak and peak > 0 else "#ffffff"
        body.append(f'  <circle class="fade" cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}" style="animation-delay: {1.2 + i * 0.02:.2f}s"/>')

    draw_style = (
        "\n    .draw { stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 1.8s ease-in-out forwards; }"
        "\n    @keyframes draw { to { stroke-dashoffset: 0; } }"
    )
    return card(width, height, f"Contribuições nos últimos {days} dias", "\n".join(body), draw_style)


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
        ("stats.svg", stats_svg(user)),
        ("top-langs.svg", top_langs_svg(user)),
        ("activity-graph.svg", activity_svg(user)),
    ):
        (args.out / name).write_text(svg, encoding="utf-8", newline="\n")
        print(f"{args.out / name}: gerado")


if __name__ == "__main__":
    main()
