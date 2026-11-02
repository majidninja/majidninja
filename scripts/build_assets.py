#!/usr/bin/env python3
"""Draw the profile cards in assets/ and refresh the generated parts of README.md.

Usage:
    GITHUB_TOKEN=... python3 scripts/build_assets.py           # write files
    GITHUB_TOKEN=... python3 scripts/build_assets.py --commit  # also commit them
                                                               # (signed, via the API)

--commit is for the weekly workflow. It uses the GraphQL createCommitOnBranch
mutation, so GitHub signs the commit and it shows as Verified.
"""

import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import OrderedDict
from xml.sax.saxutils import escape

LOGIN = os.environ.get("PROFILE_LOGIN", "majidninja")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_REPOS = ["rotcheck", "whatchanged"]

THEMES = {
    "dark": dict(bg="#0d1117", panel="#161b22", border="#30363d", fg="#e6edf3",
                 dim="#8b949e", accent="#3fb950", accent2="#58a6ff", warn="#d29922",
                 red="#f85149"),
    "light": dict(bg="#ffffff", panel="#f6f8fa", border="#d0d7de", fg="#1f2328",
                  dim="#59636e", accent="#1a7f37", accent2="#0969da", warn="#9a6700",
                  red="#cf222e"),
}
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"


# ---------------------------------------------------------------- GitHub API

def api(path, data=None):
    url = path if path.startswith("http") else "https://api.github.com" + path
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", LOGIN + "-profile")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def graphql(query, variables=None):
    out = api("/graphql", {"query": query, "variables": variables or {}})
    if out.get("errors"):
        raise SystemExit("GraphQL error: %s" % out["errors"])
    return out["data"]


def collect():
    merged = []
    page = 1
    while True:
        q = "author:%s+is:pr+is:merged+-user:%s" % (LOGIN, LOGIN)
        res = api("/search/issues?q=%s&per_page=100&page=%d&sort=created&order=desc" % (q, page))
        merged += res["items"]
        if len(merged) >= res["total_count"] or not res["items"]:
            break
        page += 1

    by_repo = OrderedDict()
    for pr in merged:
        repo = pr["repository_url"].split("/repos/", 1)[1]
        by_repo.setdefault(repo, []).append(pr)

    contrib = graphql(
        "query($l:String!){user(login:$l){contributionsCollection{"
        "contributionCalendar{totalContributions}}}}", {"l": LOGIN}
    )["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]

    repos = api("/users/%s/repos?per_page=100&type=owner" % LOGIN)
    own = [r for r in repos if not r["fork"] and r["name"] != LOGIN]
    stars = sum(r["stargazers_count"] for r in own)

    releases = OrderedDict()
    for name in RELEASE_REPOS:
        try:
            releases[name] = api("/repos/%s/%s/releases/latest" % (LOGIN, name))["tag_name"]
        except Exception:
            releases[name] = "unreleased"

    return dict(merged=len(merged), by_repo=by_repo, contrib=contrib,
                own_repos=len(own), stars=stars, releases=releases,
                date=dt.date.today().isoformat())


# ---------------------------------------------------------------- SVG cards

def svg_open(w, h, t, label):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'role="img" aria-label="%s">\n'
        "<style>text{font-family:%s} .b{font-weight:700} "
        "@keyframes blink{50%%{opacity:0}} .cur{animation:blink 1.1s step-end infinite} "
        "@keyframes led{0%%,100%%{opacity:1}40%%{opacity:.25}} "
        ".led{animation:led 1.6s ease-in-out infinite}</style>\n"
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>\n'
        % (w, h, w, h, escape(label, {'"': "&quot;"}), MONO, w - 1, h - 1, t["bg"], t["border"])
    )


def text(x, y, s, fill, size=15, cls="", anchor="start"):
    c = ' class="%s"' % cls if cls else ""
    return '<text x="%s" y="%s" fill="%s" font-size="%s" text-anchor="%s" xml:space="preserve"%s>%s</text>\n' % (
        x, y, fill, size, anchor, c, s)


def tspans(parts):
    return "".join('<tspan fill="%s"%s>%s</tspan>' % (
        f, ' class="b"' if bold else "", escape(s)) for s, f, bold in parts)


def hero(t):
    w, h = 900, 300
    out = [svg_open(w, h, t, "Terminal introducing Majid Ali, DevOps engineer, "
                             "server master and security expert, next to a server rack.")]
    # window chrome
    out.append('<rect x="1" y="1" width="%d" height="34" rx="12" fill="%s"/>\n' % (w - 2, t["panel"]))
    out.append('<rect x="1" y="22" width="%d" height="13" fill="%s"/>\n' % (w - 2, t["panel"]))
    out.append('<line x1="1" y1="35" x2="%d" y2="35" stroke="%s"/>\n' % (w - 1, t["border"]))
    for i, c in enumerate([t["red"], t["warn"], t["accent"]]):
        out.append('<circle cx="%d" cy="18" r="6" fill="%s"/>\n' % (22 + i * 20, c))
    out.append(text(450, 23, "majid@ninja: ~", t["dim"], 13, anchor="middle"))

    p = lambda: [("majid@ninja", t["accent"], True), (":", t["fg"], False),
                 ("~", t["accent2"], True), ("$ ", t["fg"], False)]
    lines = [
        p() + [("whoami --verbose", t["fg"], False)],
        [("Majid Ali", t["fg"], True)],
        [("DevOps engineer · server master · security expert", t["dim"], False)],
        [("Ramallah · majid.ninja", t["dim"], False)],
        p() + [("systemctl status majid", t["fg"], False)],
        [("● ", t["accent"], False), ("majid.service", t["fg"], True),
         (" - keeps servers up and attackers out", t["dim"], False)],
        [("     Active: ", t["dim"], False), ("active (running)", t["accent"], True),
         (" since 2023-08-31", t["dim"], False)],
        [("      Tasks: ", t["dim"], False), ("bash scripts, hardware, games", t["fg"], False)],
    ]
    y = 70
    for parts in lines:
        out.append('<text x="28" y="%d" font-size="15" xml:space="preserve">%s</text>\n' % (y, tspans(parts)))
        y += 25
    out.append('<text x="28" y="%d" font-size="15" xml:space="preserve">%s'
               '<tspan fill="%s" class="cur">█</tspan></text>\n' % (y, tspans(p()), t["fg"]))

    # server rack
    rx, ry, rw = 690, 58, 170
    out.append('<rect x="%d" y="%d" width="%d" height="214" rx="8" fill="%s" stroke="%s"/>\n'
               % (rx, ry, rw, t["panel"], t["border"]))
    for i in range(6):
        uy = ry + 12 + i * 33
        out.append('<rect x="%d" y="%d" width="%d" height="25" rx="4" fill="%s" stroke="%s"/>\n'
                   % (rx + 12, uy, rw - 24, t["bg"], t["border"]))
        for j in range(5):
            out.append('<rect x="%d" y="%d" width="10" height="3" rx="1.5" fill="%s"/>\n'
                       % (rx + 24 + j * 14, uy + 11, t["border"]))
        colors = [t["accent"], t["accent2"] if i % 2 else t["accent"]]
        for k, c in enumerate(colors):
            out.append('<circle class="led" style="animation-delay:%.1fs" cx="%d" cy="%d" r="3.5" fill="%s"/>\n'
                       % ((i * 0.37 + k * 0.8) % 1.6, rx + rw - 40 + k * 14, uy + 12.5, c))
    out.append("</svg>\n")
    return "".join(out)


def stats_alt(d):
    rel = ", ".join("%s %s" % kv for kv in d["releases"].items())
    return ("%d pull requests merged into %d other people's repositories. "
            "%d contributions in the last year. %d of my own public repos with %d stars. "
            "Latest releases: %s. Data as of %s." % (
                d["merged"], len(d["by_repo"]), d["contrib"], d["own_repos"],
                d["stars"], rel, d["date"]))


def stats(t, d):
    w, h = 900, 190
    out = [svg_open(w, h, t, stats_alt(d))]
    out.append(text(28, 38, tspans([("$ ", t["dim"], False), ("uptime --stats", t["fg"], False)]),
                    t["fg"], 15))
    tiles = [
        (str(d["merged"]), "PRs merged upstream", "into %d other repos" % len(d["by_repo"]), t["accent"]),
        (str(d["contrib"]), "contributions", "in the last year", t["accent2"]),
        (str(d["own_repos"]), "own public repos", "%d stars between them" % d["stars"], t["warn"]),
    ]
    tw, gap, x0 = 200, 16, 28
    for i, (big, label, sub, color) in enumerate(tiles):
        x = x0 + i * (tw + gap)
        out.append('<rect x="%d" y="58" width="%d" height="104" rx="8" fill="%s" stroke="%s"/>\n'
                   % (x, tw, t["panel"], t["border"]))
        out.append(text(x + 16, 104, escape(big), color, 34, "b"))
        out.append(text(x + 16, 130, escape(label), t["fg"], 13))
        out.append(text(x + 16, 149, escape(sub), t["dim"], 12))
    x = x0 + 3 * (tw + gap)
    rw = w - 28 - x
    out.append('<rect x="%d" y="58" width="%d" height="104" rx="8" fill="%s" stroke="%s"/>\n'
               % (x, rw, t["panel"], t["border"]))
    out.append(text(x + 16, 84, "latest releases", t["fg"], 13))
    for k, (name, tag) in enumerate(d["releases"].items()):
        y = 112 + k * 24
        out.append(text(x + 16, y, escape(name), t["dim"], 14))
        out.append(text(x + rw - 16, y, escape(tag), t["accent"], 14, "b", "end"))
    out.append(text(w - 28, 38, "as of " + d["date"], t["dim"], 12, anchor="end"))
    out.append("</svg>\n")
    return "".join(out)


# ---------------------------------------------------------------- README

def upstream_table(d):
    rows = ["| Project | Merged PRs | Most recent |", "| --- | --- | --- |"]
    for repo, prs in d["by_repo"].items():
        last = prs[0]
        title = last["title"].replace("|", "\\|")
        rows.append("| [%s](https://github.com/%s) | %d | [#%d](%s) %s |" % (
            repo, repo, len(prs), last["number"], last["html_url"], title))
    return "\n".join(rows)


def replace_block(readme, name, body):
    pat = re.compile(r"(<!-- %s:start -->).*?(<!-- %s:end -->)" % (name, name), re.S)
    if not pat.search(readme):
        raise SystemExit("README is missing the %s markers" % name)
    return pat.sub(lambda m: m.group(1) + "\n" + body + "\n" + m.group(2), readme)


def stats_block(d):
    return (
        '<a href="https://github.com/search?q=author%%3A%s+is%%3Apr+is%%3Amerged+-user%%3A%s&amp;type=pullrequests">\n'
        "  <picture>\n"
        '    <source media="(prefers-color-scheme: dark)" srcset="assets/stats-dark.svg">\n'
        '    <img src="assets/stats-light.svg" width="100%%" alt="%s">\n'
        "  </picture>\n"
        "</a>" % (LOGIN, LOGIN, escape(stats_alt(d), {'"': "&quot;"}))
    )


# ---------------------------------------------------------------- commit

def commit(paths):
    changed = subprocess.run(["git", "status", "--porcelain", "--"] + paths, cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
    if not changed:
        print("nothing changed")
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    adds = []
    for line in changed.splitlines():
        path = line[3:]
        with open(os.path.join(ROOT, path), "rb") as f:
            adds.append({"path": path, "contents": base64.b64encode(f.read()).decode()})
    out = graphql(
        "mutation($i:CreateCommitOnBranchInput!){createCommitOnBranch(input:$i){commit{url}}}",
        {"i": {"branch": {"repositoryNameWithOwner": repo, "branchName": branch},
               "message": {"headline": "Refresh profile cards"},
               "expectedHeadOid": head, "fileChanges": {"additions": adds}}})
    print("committed", out["createCommitOnBranch"]["commit"]["url"])


def main():
    d = collect()
    files = {}
    for mode, t in THEMES.items():
        files["assets/hero-%s.svg" % mode] = hero(t)
        files["assets/stats-%s.svg" % mode] = stats(t, d)
    with open(os.path.join(ROOT, "README.md")) as f:
        readme = f.read()
    readme = replace_block(readme, "stats-card", stats_block(d))
    readme = replace_block(readme, "upstream", upstream_table(d))
    files["README.md"] = readme
    for path, body in files.items():
        with open(os.path.join(ROOT, path), "w") as f:
            f.write(body)
    print(stats_alt(d))
    if "--commit" in sys.argv:
        commit(list(files))


if __name__ == "__main__":
    main()
