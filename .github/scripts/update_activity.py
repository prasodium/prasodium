#!/usr/bin/env python3
"""Regenerate the profile activity cards in assets/ from public GitHub data.

  activity-streak.svg    total contributions, current streak, longest streak
  activity-overview.svg  top languages (public repos) and a few headline numbers
  activity-graph.svg     contributions per week over the past year

Contribution numbers come from the public contribution calendar, the same one visitors
see on the profile (private contributions are included when the profile shares them).
Languages and stars come from the public REST API. No secrets are needed; the workflow's
built-in token is only used to raise the API rate limit. Standard library only.

If the calendar can't be read or doesn't add up, the script exits non-zero and leaves the
existing cards untouched. If only the API part fails, that card is left as it was.
"""
import collections
import datetime as dt
import html
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.request

USER = os.environ.get("GITHUB_REPOSITORY_OWNER") or "prasodium"
ASSETS = pathlib.Path(__file__).resolve().parents[2] / "assets"
UA = "activity-card-updater"

# Odyssey palette: deep maroon card, bronze accents, marble text.
BG, BORDER = "#5A1525", "#C9A25E"
NUM, LABEL, MUTED, DIV, TRACK = "#F4EBD9", "#D8B26E", "#C9A8AE", "#8B3A4A", "#722234"
FONT = '<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}</style>'
LANG_COLORS = {
    "TypeScript": "#3178C6", "JavaScript": "#F1E05A", "Python": "#3572A5", "C++": "#F34B7D",
    "C": "#7A7A7A", "Dart": "#00B4AB", "CSS": "#8A63D2", "HTML": "#E34C26", "Java": "#B07219",
    "PHP": "#4F5D95", "Shell": "#89E051", "Kotlin": "#A97BFF", "Swift": "#F05138", "Go": "#00ADD8",
    "Rust": "#DEA584", "TeX": "#5E9E3D", "CMake": "#DA3434", "Makefile": "#6FA84A",
}


# ----------------------------------------------------------------------------- fetching
def get(url, headers=None, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - retry on any network error
            last = e
            time.sleep(2 * (i + 1))
    raise SystemExit(f"could not fetch {url}: {last}")


def api(path):
    token = os.environ.get("GITHUB_TOKEN")
    hdr = {"Accept": "application/vnd.github+json"}
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    return json.loads(get(f"https://api.github.com{path}", hdr))


def parse_calendar(page):
    """Return ({date: (count, level)}, heading_total) for one contributions page."""
    tips = {}
    for m in re.finditer(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        n = re.match(r"\s*(No|\d[\d,]*)\s+contributions?", m.group(2))
        if n:
            tips[m.group(1)] = 0 if n.group(1) == "No" else int(n.group(1).replace(",", ""))
    days = {}
    for m in re.finditer(r"<td\b[^>]*>", page):
        tag = m.group(0)
        d, i, lv = (re.search(rf'\b{a}="([^"]*)"', tag) for a in ("data-date", "id", "data-level"))
        if d and i and lv and i.group(1) in tips:
            days[dt.date.fromisoformat(d.group(1))] = (tips[i.group(1)], int(lv.group(1)))
    h = re.search(r"([\d,]+)\s+contributions?\s+in\s", " ".join(page.split()))
    if not days or not h:
        raise SystemExit("calendar markup not recognised (GitHub may have changed it)")
    total = int(h.group(1).replace(",", ""))
    if sum(c for c, _ in days.values()) != total:
        raise SystemExit("calendar day counts do not add up to the page total")
    return days, total


# ----------------------------------------------------------------------------- svg helpers
esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731


def card(w, h, title, desc, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="t d"><title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>{FONT}'
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="14" fill="{BG}" stroke="{BORDER}" stroke-width="1.5"/>'
        f"{body}</svg>\n"
    )


def txt(x, y, s, size=12, fill=NUM, anchor="start", weight="400"):
    return f'<text x="{x:.1f}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{esc(s)}</text>'


def fmt_range(a, b, with_year):
    f = lambda d: f"{d.strftime('%b')} {d.day}"  # noqa: E731
    s = f(a) if a == b else f"{f(a)} - {f(b)}"
    return f"{s}, {b.year}" if with_year else s


def streak_card(total, since, cur, cur_rng, best, best_rng):
    W, H = 800, 170
    colw = W / 3
    cx = [colw / 2, colw * 1.5, colw * 2.5]
    o = [f'<line x1="{colw:.1f}" y1="30" x2="{colw:.1f}" y2="140" stroke="{DIV}"/>',
         f'<line x1="{2*colw:.1f}" y1="30" x2="{2*colw:.1f}" y2="140" stroke="{DIV}"/>']
    o += [txt(cx[0], 84, f"{total:,}", 38, NUM, "middle", "700"),
          txt(cx[0], 128, "Total Contributions", 14, LABEL, "middle", "600"),
          txt(cx[0], 148, f"{since.strftime('%b')} {since.day}, {since.year} - Present", 12, MUTED, "middle")]
    # ring with a gap at the top for the flame
    r, cy = 38, 68
    circ = 2 * math.pi * r
    gap = 36.0
    rot = 270 - (360 - (gap / r) * 180 / math.pi / 2)
    o.append(f'<circle cx="{cx[1]:.1f}" cy="{cy}" r="{r}" fill="none" stroke="{LABEL}" stroke-width="5" stroke-linecap="round" '
             f'stroke-dasharray="{circ-gap:.1f} {gap:.1f}" transform="rotate({rot:.1f} {cx[1]:.1f} {cy})"/>')
    fx, fy = cx[1], cy - r + 4
    o.append(f'<path transform="translate({fx:.1f} {fy})" fill="{LABEL}" '
             'd="M0 -15 C6 -8 10 -3 10 3 A10 10 0 0 1 -10 3 C-10 -2 -6 -6 0 -15 Z"/>')
    o += [txt(cx[1], 80, cur, 34, NUM, "middle", "700"),
          txt(cx[1], 128, "Current Streak", 14, LABEL, "middle", "600"),
          txt(cx[1], 148, cur_rng, 12, MUTED, "middle")]
    o += [txt(cx[2], 84, best, 38, NUM, "middle", "700"),
          txt(cx[2], 128, "Longest Streak", 14, LABEL, "middle", "600"),
          txt(cx[2], 148, best_rng, 12, MUTED, "middle")]
    return card(W, H, "GitHub streak",
                f"{total} contributions since {since.year}; current streak {cur} days; longest streak {best} days", "".join(o))


def overview_card(langs, rows):
    W, H = 800, 216
    o = [f'<line x1="400" y1="26" x2="400" y2="190" stroke="{DIV}"/>',
         txt(28, 38, "Top languages", 14, LABEL, weight="600"), txt(28, 56, "public repositories", 11, MUTED),
         txt(428, 38, "Overview", 14, LABEL, weight="600"), txt(428, 56, "past year unless noted", 11, MUTED)]
    for i, (name, pct) in enumerate(langs):
        y = 84 + i * 26
        col = LANG_COLORS.get(name, BORDER)
        o += [txt(28, y + 4, name, 12), f'<rect x="120" y="{y-6}" width="200" height="10" rx="5" fill="{TRACK}"/>',
              f'<rect x="120" y="{y-6}" width="{max(6, 200*pct/100):.1f}" height="10" rx="5" fill="{col}"/>',
              txt(336, y + 4, f"{pct:.1f}%", 11, MUTED)]
    for i, (label, value) in enumerate(rows):
        y = 84 + i * 26
        o += [txt(428, y + 4, label, 12, NUM), txt(772, y + 4, value, 13, LABEL, "end", "700")]
    return card(W, H, "Languages and overview",
                "Top languages: " + ", ".join(f"{n} {p:.0f}%" for n, p in langs) + ". " + ", ".join(f"{a} {b}" for a, b in rows), "".join(o))


def nice_top(peak):
    for step in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if math.ceil(peak / step) <= 4:
            return step, max(1, math.ceil(peak / step)) * step
    return 1000, math.ceil(peak / 1000) * 1000


def graph_card(weeks, starts, updated):
    W, H = 800, 216
    X0, X1, Y0, Y1 = 56, 772, 80, 168       # chart box: left/right/top/bottom
    step, top = nice_top(max(weeks))
    px = lambda i: X0 + (X1 - X0) * i / (len(weeks) - 1)  # noqa: E731
    py = lambda v: Y1 - (Y1 - Y0) * v / top               # noqa: E731
    o = [txt(28, 38, "Contribution graph", 14, LABEL, weight="600"), txt(28, 56, "contributions per week, past year", 11, MUTED)]
    for v in range(0, top + 1, step):
        dash = "" if v == 0 else ' stroke-dasharray="3 4"'
        o += [f'<line x1="{X0}" y1="{py(v):.1f}" x2="{X1}" y2="{py(v):.1f}" stroke="{DIV}" stroke-width="1"{dash}/>',
              txt(X0 - 8, f"{py(v)+4:.1f}", str(v), 10, MUTED, "end")]
    pts = [(px(i), py(v)) for i, v in enumerate(weeks)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    o.append(f'<polygon points="{X0},{Y1} {line} {X1},{Y1}" fill="{LABEL}" fill-opacity="0.22"/>')
    o.append(f'<polyline points="{line}" fill="none" stroke="{LABEL}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    pk = max(range(len(weeks)), key=weeks.__getitem__)
    o += [f'<circle cx="{pts[pk][0]:.1f}" cy="{pts[pk][1]:.1f}" r="4" fill="{NUM}" stroke="{LABEL}" stroke-width="2"/>',
          txt(min(pts[pk][0], X1 - 8), f"{pts[pk][1]-10:.1f}", str(weeks[pk]), 11, NUM, "end", "700")]
    last = -10
    for i, d0 in enumerate(starts):
        if (i == 0 or d0.month != starts[i - 1].month) and i - last >= 3:
            o.append(txt(px(i), 192, d0.strftime("%b"), 10, MUTED, "middle"))
            last = i
    o.append(txt(772, 38, f"Updated {updated.strftime('%b')} {updated.day}, {updated.year}", 10, MUTED, "end"))
    return card(W, H, "Contribution graph", f"Contributions per week over the past year; busiest week {weeks[pk]}.", "".join(o))


# ----------------------------------------------------------------------------- output
def previous_since():
    """The 'since' date already printed on the streak card, used if the profile API is unavailable."""
    path = ASSETS / "activity-streak.svg"
    if path.exists():
        m = re.search(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4}) - Present", path.read_text(encoding="utf-8"))
        if m:
            return dt.datetime.strptime(" ".join(m.groups()), "%b %d %Y").date()
    return dt.date(2023, 1, 1)


def write_if_changed(name, svg):
    path = ASSETS / name
    strip = lambda s: re.sub(r"Updated [^<]*", "", s)  # noqa: E731 - the date alone never triggers a commit
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if strip(old) == strip(svg):
        print(f"  {name}: no change")
        return
    ASSETS.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    print(f"  {name}: updated")


def main():
    recent, recent_total = parse_calendar(get(f"https://github.com/users/{USER}/contributions"))
    window = sorted(recent)
    today = window[-1]
    if len(window) < 350 or window[0].weekday() != 6:
        raise SystemExit("unexpected calendar window")

    try:
        created = dt.date.fromisoformat(api(f"/users/{USER}")["created_at"][:10])
    except (SystemExit, KeyError, TypeError, ValueError):
        created = previous_since()  # API hiccup: keep the join date already on the card

    counts = {}
    for y in range(created.year, today.year + 1):
        yd, _ = parse_calendar(get(f"https://github.com/users/{USER}/contributions?from={y}-01-01&to={y}-12-31"))
        counts.update({d: c for d, (c, _) in yd.items() if d <= today})
    counts.update({d: c for d, (c, _) in recent.items()})  # freshest data wins
    days = sorted(counts.items())

    best = (0, None, None)
    run, start = 0, None
    for d, n in days:
        if n:
            start = start if run else d
            run += 1
            if run >= best[0]:
                best = (run, start, d)
        else:
            run = 0
    cur, cstart, cend = 0, None, None
    for d, n in reversed(days):
        if n:
            cur, cstart, cend = cur + 1, d, cend or d
        elif d != today:
            break

    cur_rng = fmt_range(cstart, cend, cend.year != today.year) if (cur and cstart and cend) else "No current streak"
    best_rng = fmt_range(best[1], best[2], True) if (best[0] and best[1] and best[2]) else "-"

    print("cards:")
    write_if_changed("activity-streak.svg", streak_card(sum(counts.values()), created, cur, cur_rng, best[0], best_rng))

    first = window[0]
    weeks = [0] * ((len(window) + 6) // 7)
    for d in window:
        weeks[(d - first).days // 7] += recent[d][0]
    starts = [first + dt.timedelta(days=7 * i) for i in range(len(weeks))]
    write_if_changed("activity-graph.svg", graph_card(weeks, starts, today))

    # languages and stars need the REST API; if it is unavailable keep the previous card
    try:
        repos = [r for r in api(f"/users/{USER}/repos?per_page=100&type=owner") if not r["fork"]]
        bytes_by_lang = collections.Counter()
        for r in repos:
            bytes_by_lang.update(api(f"/repos/{r['full_name']}/languages"))
        total_bytes = sum(bytes_by_lang.values()) or 1
        langs = [(n, 100 * b / total_bytes) for n, b in bytes_by_lang.most_common(5)]
        months = collections.Counter()
        for d in window:
            months[(d.year, d.month)] += recent[d][0]
        (by, bm), bn = max(months.items(), key=lambda kv: kv[1])
        rows = [("Contributions", f"{recent_total:,}"),
                ("Active days", str(sum(1 for d in window if recent[d][0] > 0))),
                ("Best month", f"{dt.date(by, bm, 1).strftime('%b %Y')} ({bn})"),
                ("Public repositories", str(len(repos))),
                ("Stars earned", str(sum(r["stargazers_count"] for r in repos)))]
        write_if_changed("activity-overview.svg", overview_card(langs, rows))
    except (SystemExit, KeyError, TypeError) as e:
        print(f"  activity-overview.svg: skipped ({e}); keeping the previous card")
        if not (ASSETS / "activity-overview.svg").exists():
            raise SystemExit("no previous overview card to keep")


if __name__ == "__main__":
    sys.exit(main())
