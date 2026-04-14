#!/usr/bin/env python3
"""
Multi-repo git contributor report generator.
Scans all git repos under a directory, merges stats, outputs HTML report.

Usage:
    python3 codereport.py --since "7 days ago"
    python3 codereport.py --since "2026-04-07" --until "2026-04-14"
    python3 codereport.py --since "30 days ago" --dir /path/to/repos
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

try:
    from pygments import lex
    from pygments.lexers import get_lexer_for_filename
    from pygments.util import ClassNotFound
    from pygments.token import Token
except ImportError:
    print("pip install pygments", file=sys.stderr)
    sys.exit(1)

CODE_EXTS = {".swift", ".m", ".h", ".mm", ".py", ".js", ".ts", ".tsx", ".jsx",
             ".go", ".rs", ".java", ".kt", ".c", ".cpp", ".cc", ".cs", ".rb",
             ".php", ".scala", ".sh", ".bash", ".zsh", ".vue", ".svelte"}
SKIP_EXTS = {
    ".strings", ".json", ".md", ".plist", ".pbxproj", ".yml", ".yaml",
    ".xcconfig", ".txt", ".csv", ".html", ".css", ".xml", ".entitlements",
    ".xcscheme", ".svg", ".png", ".jpg", ".gif", ".icns", ".ttf", ".otf",
    ".storyboard", ".xib", ".xcworkspacedata", ".lock", ".bundle", ".framework",
    ".pdf", ".mo", ".po", ".map", ".min.js", ".min.css", ".snap",
}
SKIP_DIRS = {"Pods/", "node_modules/", "vendor/", "build/", "DerivedData/",
             ".github/", "dist/", "coverage/", ".next/", ".nuxt/", "target/",
             "__pycache__/", ".gradle/", ".idea/", ".xcassets/", "Generated/",
             "generated/", "auto_generated/", ".pb.go", ".gen.go"}

EXCLUDE_PATHSPECS = [
    ":(exclude)*.strings", ":(exclude)*.json", ":(exclude)*.md",
    ":(exclude)*.plist", ":(exclude)*.pbxproj", ":(exclude)*.yml",
    ":(exclude)*.yaml", ":(exclude)*.xcconfig", ":(exclude)*.txt",
    ":(exclude)*.storyboard", ":(exclude)*.xib", ":(exclude)*.xml",
    ":(exclude)*.entitlements", ":(exclude)*.svg", ":(exclude)*.lock",
    ":(exclude)*.xcworkspacedata", ":(exclude)*.xcscheme",
    ":(exclude)*.css", ":(exclude)*.html", ":(exclude)*.map",
    ":(exclude)*.snap", ":(exclude)*.po", ":(exclude)*.mo",
    ":(exclude)*.min.js", ":(exclude)*.min.css", ":(exclude)*.lottie",
    ":(exclude)*.pb.go", ":(exclude)*.gen.go", ":(exclude)*_generated.go",
    ":(exclude)*.pb.ts", ":(exclude)*.d.ts",
    ":(exclude)Pods/*", ":(exclude)node_modules/*", ":(exclude)vendor/*",
    ":(exclude)Generated/*", ":(exclude)generated/*",
    ":(exclude)*.xcassets/*", ":(exclude)*.bundle/*", ":(exclude)*.framework/*",
    ":(exclude)package-lock.json", ":(exclude)yarn.lock", ":(exclude)pnpm-lock.yaml",
    ":(exclude)Podfile.lock", ":(exclude)go.sum",
]

RENAME_FLAGS = ["-c", "diff.renameLimit=20000", "-c", "merge.renameLimit=20000"]
RENAME_DETECT = ["-M", "-C", "--find-renames=40%"]

COMMENT_STARTS = ("//", "/*", "*/", "///", "*")
PREPROC_STARTS = ("#pragma", "#import", "#include", "#if ", "#endif", "#else",
                  "#define", "#if@", "#warning", "#error")


def run(cmd: List[str], cwd: str, timeout: int = 120) -> str:
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8", errors="replace", check=False,
                       timeout=timeout)
    return r.stdout


def is_code_file(path: str) -> bool:
    for d in SKIP_DIRS:
        if d in path:
            return False
    ext = os.path.splitext(path)[1].lower()
    return ext in CODE_EXTS


def is_code_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith(COMMENT_STARTS):
        return False
    if s.startswith("*") and not s.startswith("*("):
        return False
    if s.startswith(PREPROC_STARTS):
        return False
    return True


def find_repos(root: str) -> List[str]:
    repos = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            repos.append(dirpath)
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "Pods",
                        "vendor", "build", "DerivedData", ".gradle", ".idea", "__pycache__",
                        "dist", "coverage", ".next", ".nuxt", "target"}]
    return sorted(repos)


DEFAULT_AUTHORS_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "authors.json")

# Populated from the JSON config at startup. Maps any known alias (or canonical
# name) to the canonical display name. Unknown names pass through unchanged.
AUTHOR_ALIASES: Dict[str, str] = {}


def normalize_author(name: str) -> str:
    return AUTHOR_ALIASES.get(name, name)


def load_authors_config(path: str) -> dict:
    """Load the authors config and populate AUTHOR_ALIASES. Missing file is OK."""
    global AUTHOR_ALIASES
    AUTHOR_ALIASES = {}
    if not os.path.exists(path):
        return {"authors": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: could not read authors config {path}: {e}", file=sys.stderr)
        return {"authors": []}
    for entry in config.get("authors", []):
        canon = entry.get("canonical")
        if not canon:
            continue
        AUTHOR_ALIASES[canon] = canon
        for alias in entry.get("aliases", []) or []:
            AUTHOR_ALIASES[alias] = canon
    return config


def update_authors_config(path: str, config: dict, seen: Dict[str, Set[str]]) -> int:
    """Merge newly-seen (name -> emails) pairs into config and persist if changed.

    New names are added with canonical = raw git name and empty aliases — the
    user can later edit the JSON to fold duplicates under a shared canonical
    name. Returns the number of additions (for logging)."""
    authors = config.setdefault("authors", [])
    by_name: Dict[str, dict] = {}
    for entry in authors:
        canon = entry.get("canonical")
        if not canon:
            continue
        by_name[canon] = entry
        for alias in entry.get("aliases", []) or []:
            by_name[alias] = entry

    changes = 0
    for name, emails in seen.items():
        if not name:
            continue
        entry = by_name.get(name)
        if entry is None:
            entry = {"canonical": name, "aliases": [], "emails": []}
            authors.append(entry)
            by_name[name] = entry
            changes += 1
        existing = set(entry.get("emails", []) or [])
        for email in sorted(e for e in emails if e and e not in existing):
            entry.setdefault("emails", []).append(email)
            changes += 1

    if changes:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except OSError as e:
            print(f"Warning: could not write authors config {path}: {e}", file=sys.stderr)
    return changes


def get_repo_remote_url(repo: str) -> Optional[str]:
    """Return a normalized https://github.com/<owner>/<repo> URL, or None.

    Handles the three common remote formats: HTTPS, scp-style SSH, and ssh://.
    Non-GitHub remotes (GitLab, self-hosted, etc.) still get a best-effort URL —
    the caller can treat any returned value as a clickable link."""
    out = run(["git", "remote", "get-url", "origin"], cwd=repo, timeout=10).strip()
    if not out:
        return None
    url = out
    if url.endswith(".git"):
        url = url[:-4]
    # scp-style: git@github.com:owner/repo
    m = re.match(r'^[^@]+@([^:]+):(.+)$', url)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    # ssh://git@github.com/owner/repo
    m = re.match(r'^ssh://[^@]+@([^/]+)/(.+)$', url)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    # already https:// or http://
    if url.startswith(("https://", "http://")):
        return url
    return None


def get_last_commit_in_window(repo: str, since: str, until: str) -> Optional[Dict[str, str]]:
    """Return {hash, short, iso_date, subject} for the most recent commit in window, or None."""
    out = run(["git", "log", "--all", f"--since={since}", f"--until={until}",
               "--no-merges", "-1", "--format=%H%x1f%h%x1f%aI%x1f%s"], cwd=repo, timeout=15).strip()
    if not out or "\x1f" not in out:
        return None
    parts = out.split("\x1f", 3)
    if len(parts) < 4:
        return None
    return {"hash": parts[0], "short": parts[1], "iso_date": parts[2], "subject": parts[3]}


def merge_daily_commit_totals(per_repo: Dict[str, Dict[str, Dict[str, int]]]) -> Dict[str, int]:
    """Collapse {repo: {date: {author: count}}} into {date: total_commits}."""
    out: Dict[str, int] = defaultdict(int)
    for _, by_date in per_repo.items():
        for date, authors in by_date.items():
            out[date] += sum(authors.values())
    return dict(out)


def merge_per_author_daily_commits(per_repo: Dict[str, Dict[str, Dict[str, int]]]) -> Dict[str, Dict[str, int]]:
    """Collapse {repo: {date: {author: count}}} into {author: {date: total_count}}.

    get_daily_commits() has already normalized author names, so we just fold
    the per-repo dicts together."""
    out: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for _, by_date in per_repo.items():
        for date, authors in by_date.items():
            for author, cnt in authors.items():
                out[author][date] += cnt
    return {a: dict(dc) for a, dc in out.items()}


def collect_author_identities(repo: str, since: str, until: str) -> Dict[str, Set[str]]:
    """Return {raw_author_name: {email, ...}} for commits in the window."""
    out = run(["git", "log", "--all", f"--since={since}", f"--until={until}",
               "--format=%an|%ae", "--no-merges"], cwd=repo)
    seen: Dict[str, Set[str]] = defaultdict(set)
    for line in out.splitlines():
        if "|" not in line:
            continue
        name, email = line.split("|", 1)
        seen[name.strip()].add(email.strip())
    return seen


def get_raw_stats(repo: str, since: str, until: str) -> Dict[str, Dict[str, int]]:
    out = run(["git"] + RENAME_FLAGS + ["log", "--all", f"--since={since}", f"--until={until}",
               "--format=COMMIT_START %H %an", "--shortstat", "--no-merges"]
              + RENAME_DETECT
              + ["--"] + ["."] + EXCLUDE_PATHSPECS, cwd=repo)
    stats = defaultdict(lambda: {"commits": 0, "ins": 0, "del": 0})
    current_author = None
    for line in out.splitlines():
        m = re.match(r'^COMMIT_START [0-9a-f]+ (.+)$', line)
        if m:
            current_author = normalize_author(m.group(1))
            stats[current_author]["commits"] += 1
            continue
        if current_author:
            m2 = re.search(r'(\d+) insertion', line)
            if m2:
                stats[current_author]["ins"] += int(m2.group(1))
            m3 = re.search(r'(\d+) deletion', line)
            if m3:
                stats[current_author]["del"] += int(m3.group(1))
    return dict(stats)


def get_effective_stats(repo: str, since: str, until: str) -> Dict[str, Dict[str, int]]:
    dump = run(["git"] + RENAME_FLAGS + ["log", "--all", f"--since={since}", f"--until={until}",
                '--format=COMMIT_START %H %an', "-p", "--no-color", "--no-merges"]
               + RENAME_DETECT
               + ["--", "."] + EXCLUDE_PATHSPECS,
               cwd=repo, timeout=300)

    commits = _parse_diff(dump)
    stats = defaultdict(lambda: {"ins": 0, "del": 0, "files": set()})

    for commit_hash, (author, files) in commits.items():
        author = normalize_author(author)
        for filepath, changes in files.items():
            plus_lines = changes['+']
            minus_lines = changes['-']
            eff_add = sum(1 for l in plus_lines if is_code_line(l)) if plus_lines else 0
            eff_del = sum(1 for l in minus_lines if is_code_line(l)) if minus_lines else 0
            if eff_add > 0 or eff_del > 0:
                stats[author]["ins"] += eff_add
                stats[author]["del"] += eff_del
                stats[author]["files"].add(filepath)

    return {a: {"ins": s["ins"], "del": s["del"], "files": len(s["files"])} for a, s in stats.items()}


def _parse_diff(dump: str) -> Dict[str, Tuple[str, Dict[str, Dict[str, List[str]]]]]:
    result = {}
    current_hash = None
    current_author = None
    current_file = None
    current_plus = []
    current_minus = []
    commit_re = re.compile(r'^COMMIT_START ([0-9a-f]+) (.+)$')

    def flush():
        nonlocal current_file, current_plus, current_minus
        if current_hash and current_file and is_code_file(current_file):
            if current_hash not in result:
                result[current_hash] = (current_author, {})
            result[current_hash][1][current_file] = {'+': current_plus[:], '-': current_minus[:]}

    for line in dump.splitlines():
        m = commit_re.match(line)
        if m:
            flush()
            current_hash = m.group(1)
            current_author = m.group(2)
            current_file = None
            current_plus = []
            current_minus = []
            continue
        if line.startswith("+++ b/"):
            flush()
            current_file = line[6:]
            current_plus = []
            current_minus = []
            continue
        if line.startswith("--- a/"):
            continue
        if not current_file:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_plus.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            current_minus.append(line[1:])
    flush()
    return result


def get_daily_commits(repo: str, since: str, until: str) -> Dict[str, Dict[str, int]]:
    out = run(["git", "log", "--all", f"--since={since}", f"--until={until}",
               "--format=%ad|%an", "--date=short", "--no-merges"], cwd=repo)
    daily = defaultdict(lambda: defaultdict(int))
    for line in out.splitlines():
        if "|" not in line:
            continue
        date, author = line.split("|", 1)
        author = normalize_author(author.strip())
        daily[date][author] += 1
    return dict(daily)


def get_daily_lines(repo: str, since: str, until: str) -> Dict[str, Dict[str, Dict[str, int]]]:
    out = run(["git"] + RENAME_FLAGS + ["log", "--all", f"--since={since}", f"--until={until}",
               "--format=DAY_START %ad %an", "--date=short", "--shortstat", "--no-merges"]
              + RENAME_DETECT
              + ["--", "."] + EXCLUDE_PATHSPECS, cwd=repo)
    daily = defaultdict(lambda: defaultdict(lambda: {"ins": 0, "del": 0}))
    current_date = None
    current_author = None
    for line in out.splitlines():
        m = re.match(r'^DAY_START (\d{4}-\d{2}-\d{2}) (.+)$', line)
        if m:
            current_date = m.group(1)
            current_author = normalize_author(m.group(2))
            continue
        if current_date and current_author:
            m2 = re.search(r'(\d+) insertion', line)
            if m2:
                daily[current_date][current_author]["ins"] += int(m2.group(1))
            m3 = re.search(r'(\d+) deletion', line)
            if m3:
                daily[current_date][current_author]["del"] += int(m3.group(1))
    return {d: dict(authors) for d, authors in daily.items()}


def get_total_commits(repo: str, since: str, until: str) -> int:
    out = run(["git", "log", "--all", f"--since={since}", f"--until={until}",
               "--format=oneline", "--no-merges"], cwd=repo)
    return len([l for l in out.splitlines() if l.strip()])


def get_author_commits(repo: str, since: str, until: str) -> List[dict]:
    """Collect per-commit metadata (sha, author, message, numstat files) for the review dump.

    We use a unique header delimiter so numstat rows (which are newline-separated after the
    header) can be grouped back under their owning commit without parsing ambiguity.
    """
    # \x01 (SOH) cannot legally appear in a git format string via subprocess args, so we use
    # a printable sentinel prefix. Commit subjects cannot start with this exact sequence in
    # practice, and numstat rows are tab-separated so won't match.
    DELIM = "@@CR_COMMIT@@"
    fmt = f"{DELIM}%H|%h|%an|%ae|%aI|%s"
    out = run(["git", "log", "--all", "--no-merges", f"--since={since}", f"--until={until}",
               "--numstat", f"--format={fmt}"], cwd=repo)
    commits: List[dict] = []
    current: Optional[dict] = None
    for line in out.split("\n"):
        if line.startswith(DELIM):
            if current:
                commits.append(current)
            parts = line[len(DELIM):].split("|", 5)
            if len(parts) != 6:
                current = None
                continue
            sha, short, name, email, date, subject = parts
            current = {
                "sha": sha, "short": short,
                "author": normalize_author(name), "raw_author": name, "email": email,
                "date": date, "subject": subject,
                "files": [], "insertions": 0, "deletions": 0,
            }
        elif current and line.strip() and "\t" in line:
            segs = line.split("\t", 2)
            if len(segs) != 3:
                continue
            ins_s, del_s, path = segs
            try:
                ins = 0 if ins_s == "-" else int(ins_s)
                d = 0 if del_s == "-" else int(del_s)
            except ValueError:
                continue
            current["files"].append({"path": path, "ins": ins, "del": d})
            current["insertions"] += ins
            current["deletions"] += d
    if current:
        commits.append(current)
    return commits


AUTHOR_COLORS = {
    "Kidd": "#79c0ff", "Sol": "#f97583", "Tim": "#d2a8ff",
    "ngn999": "#ffa657", "Jack": "#7ee787", "mitsui": "#a5d6ff",
    "tiechou": "#ff7b72", "sunbaoyin": "#d29922",
}
DEFAULT_COLORS = ["#79c0ff", "#f97583", "#d2a8ff", "#ffa657", "#7ee787", "#a5d6ff", "#ff7b72", "#d29922"]


def get_color(author: str) -> str:
    if author in AUTHOR_COLORS:
        return AUTHOR_COLORS[author]
    idx = hash(author) % len(DEFAULT_COLORS)
    return DEFAULT_COLORS[idx]


def generate_html(report_data: dict, output_path: str):
    d = report_data
    authors = d["authors"]
    sorted_authors = sorted(authors.keys(), key=lambda a: authors[a].get("eff_ins", 0) + authors[a].get("eff_del", 0), reverse=True)
    color_map = {a: get_color(a) for a in sorted_authors}

    total_commits = d["total_commits"]
    raw_ins = sum(a["raw_ins"] for a in authors.values())
    raw_del = sum(a["raw_del"] for a in authors.values())
    eff_ins = sum(a["eff_ins"] for a in authors.values())
    eff_del = sum(a["eff_del"] for a in authors.values())
    eff_net = eff_ins - eff_del
    raw_net = raw_ins - raw_del
    code_commits = sum(1 for a in authors.values() if a["eff_ins"] > 0 or a["eff_del"] > 0)
    filter_pct = f"-{(1 - eff_ins / raw_ins) * 100:.1f}%" if raw_ins > 0 else "N/A"

    period_label = d["period_label"]
    since_label = d["since"]
    until_label = d["until"]
    repos_count = d["repos_count"]

    daily_data = d.get("daily_lines", {})
    all_dates = sorted(daily_data.keys())

    def fmt_date(date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        return f"周{weekdays[dt.weekday()]} {dt.day}日"

    daily_labels = [fmt_date(d) for d in all_dates]

    daily_js_data = []
    for date_str in all_dates:
        entry = {"d": fmt_date(date_str)}
        for a in sorted_authors:
            entry[a] = daily_data.get(date_str, {}).get(a, {}).get("ins", 0) - daily_data.get(date_str, {}).get(a, {}).get("del", 0)
        daily_js_data.append(entry)

    daily_js_parts = ",".join(
        "{" + ",".join([f'd:"{e["d"]}"'] + [f'{a[:2].lower()}:{e.get(a,0)}' for a in sorted_authors[:8]]) + "}"
        for e in daily_js_data
    )

    legend_items = "\n".join(
        f'<div class="legend-item"><div class="legend-dot" style="background:{color_map[a]}"></div>{a}</div>'
        for a in sorted_authors[:8]
    )

    # Daily commit-count line chart (pure SVG, no JS).
    # Y-axis: commit count; X-axis: calendar dates in the window.
    import math as _math

    def _nice_ceil(v: float) -> int:
        """Round up to a human-friendly tick max (1, 2, 5 × 10^n)."""
        if v <= 0:
            return 1
        exp = _math.floor(_math.log10(v))
        base = 10 ** exp
        frac = v / base
        if frac <= 1:
            return int(1 * base)
        if frac <= 2:
            return int(2 * base)
        if frac <= 5:
            return int(5 * base)
        return int(10 * base)

    daily_commits = d.get("daily_commits", {}) or {}
    commit_series = [(ds, int(daily_commits.get(ds, 0))) for ds in all_dates]
    raw_max = max((c for _, c in commit_series), default=0)
    y_max = _nice_ceil(raw_max) if raw_max > 0 else 1

    SVG_W, SVG_H = 1000, 260
    PAD_L, PAD_R, PAD_T, PAD_B = 40, 16, 20, 32
    chart_w = SVG_W - PAD_L - PAD_R
    chart_h = SVG_H - PAD_T - PAD_B
    n = len(commit_series)

    def _x(i: int) -> float:
        if n <= 1:
            return PAD_L + chart_w / 2
        return PAD_L + (chart_w * i / (n - 1))

    def _y(v: float) -> float:
        return PAD_T + chart_h * (1 - (v / y_max))

    # Gridlines + Y labels (5 ticks: 0, 25%, 50%, 75%, 100%)
    grid_parts = []
    for i in range(5):
        frac = i / 4
        yv = y_max * (1 - frac)
        yy = PAD_T + chart_h * frac
        grid_parts.append(
            f'<line x1="{PAD_L}" y1="{yy:.1f}" x2="{PAD_L + chart_w}" y2="{yy:.1f}" '
            f'stroke="var(--border-soft)" stroke-width="1" stroke-dasharray="{"0" if i == 4 else "2,3"}"/>'
        )
        grid_parts.append(
            f'<text x="{PAD_L - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'fill="var(--muted-2)" font-size="10" font-family="JetBrains Mono, monospace">{int(yv):,}</text>'
        )

    # X-axis labels: sample down if too many dates to avoid overlap.
    x_label_parts = []
    if n > 0:
        step = max(1, (n + 9) // 10)  # show at most ~10-11 labels
        for i, (ds, _) in enumerate(commit_series):
            if i % step != 0 and i != n - 1:
                continue
            try:
                dt = datetime.strptime(ds, "%Y-%m-%d")
                label = dt.strftime("%m-%d")
            except ValueError:
                label = ds
            x_label_parts.append(
                f'<text x="{_x(i):.1f}" y="{PAD_T + chart_h + 18}" text-anchor="middle" '
                f'fill="var(--muted)" font-size="10" font-family="JetBrains Mono, monospace">{label}</text>'
            )

    # Area fill + line + points.
    path_points = " ".join(f"{_x(i):.1f},{_y(v):.1f}" for i, (_, v) in enumerate(commit_series))
    area_path = ""
    if n >= 2:
        first_x = _x(0)
        last_x = _x(n - 1)
        base_y = PAD_T + chart_h
        area_d = (
            f"M {first_x:.1f},{base_y:.1f} "
            + " ".join(f"L {_x(i):.1f},{_y(v):.1f}" for i, (_, v) in enumerate(commit_series))
            + f" L {last_x:.1f},{base_y:.1f} Z"
        )
        area_path = f'<path d="{area_d}" fill="url(#commitGradient)" opacity="0.6"/>'

    line_el = ""
    if n >= 2:
        line_el = (
            f'<polyline points="{path_points}" fill="none" stroke="var(--accent)" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    point_parts = []
    for i, (ds, v) in enumerate(commit_series):
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d")
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            tip = f"{dt.strftime('%Y-%m-%d')} 周{weekdays[dt.weekday()]} · {v} 次提交"
        except ValueError:
            tip = f"{ds}: {v} 次提交"
        point_parts.append(
            f'<circle class="pt" cx="{_x(i):.1f}" cy="{_y(v):.1f}" r="3.5" '
            f'fill="var(--bg)" stroke="var(--accent)" stroke-width="2">'
            f'<title>{tip}</title></circle>'
        )

    axis_el = (
        f'<line x1="{PAD_L}" y1="{PAD_T + chart_h}" x2="{PAD_L + chart_w}" y2="{PAD_T + chart_h}" '
        f'stroke="var(--border)" stroke-width="1"/>'
    )

    empty_el = ""
    if raw_max == 0:
        empty_el = (
            f'<text x="{SVG_W / 2}" y="{PAD_T + chart_h / 2}" text-anchor="middle" '
            f'fill="var(--muted-2)" font-size="12">（该时段无提交）</text>'
        )

    total_commits_in_window = sum(v for _, v in commit_series)
    avg_commits = total_commits_in_window / n if n else 0
    peak_day = max(commit_series, key=lambda x: x[1]) if commit_series else (None, 0)

    commit_chart_svg = f'''
      <svg viewBox="0 0 {SVG_W} {SVG_H}" preserveAspectRatio="none" width="100%" height="{SVG_H}"
           role="img" aria-label="每日提交次数折线图">
        <defs>
          <linearGradient id="commitGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/>
          </linearGradient>
        </defs>
        {"".join(grid_parts)}
        {area_path}
        {line_el}
        {axis_el}
        {"".join(point_parts)}
        {"".join(x_label_parts)}
        {empty_el}
      </svg>'''

    commit_chart_summary = (
        f'<div class="chart-summary">'
        f'<span><span class="label">总提交</span> <strong class="mono">{total_commits_in_window:,}</strong></span>'
        f'<span><span class="label">日均</span> <strong class="mono">{avg_commits:.1f}</strong></span>'
        + (
            f'<span><span class="label">峰值</span> <strong class="mono">{peak_day[1]}</strong> '
            f'<span class="label">（{peak_day[0]}）</span></span>'
            if peak_day[0] and peak_day[1] > 0 else ""
        )
        + '</div>'
    )

    # Per-author multi-line chart: every contributor gets one colored polyline
    # on the same axes as the total-commit chart above, so individual rhythms
    # can be compared directly against each other and against the aggregate.
    per_author_daily = d.get("per_author_daily", {}) or {}
    author_commit_totals = [(a, sum(dc.values())) for a, dc in per_author_daily.items() if sum(dc.values()) > 0]
    author_commit_totals.sort(key=lambda x: x[1], reverse=True)

    pa_raw_max = 0
    for a, _ in author_commit_totals:
        dc = per_author_daily.get(a, {})
        for ds in all_dates:
            pa_raw_max = max(pa_raw_max, int(dc.get(ds, 0)))
    pa_y_max = _nice_ceil(pa_raw_max) if pa_raw_max > 0 else 1

    # Reuse main-chart dimensions and coordinate helpers so the two charts
    # line up when scrolled side by side.
    def _pa_y(v: float) -> float:
        return PAD_T + chart_h * (1 - (v / pa_y_max))

    pa_grid_parts = []
    for i in range(5):
        frac = i / 4
        yv = pa_y_max * (1 - frac)
        yy = PAD_T + chart_h * frac
        pa_grid_parts.append(
            f'<line x1="{PAD_L}" y1="{yy:.1f}" x2="{PAD_L + chart_w}" y2="{yy:.1f}" '
            f'stroke="var(--border-soft)" stroke-width="1" stroke-dasharray="{"0" if i == 4 else "2,3"}"/>'
        )
        pa_grid_parts.append(
            f'<text x="{PAD_L - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'fill="var(--muted-2)" font-size="10" font-family="JetBrains Mono, monospace">{int(yv):,}</text>'
        )

    pa_x_label_parts = []
    if n > 0:
        step = max(1, (n + 9) // 10)
        for i, (ds, _) in enumerate(commit_series):
            if i % step != 0 and i != n - 1:
                continue
            try:
                dt = datetime.strptime(ds, "%Y-%m-%d")
                label = dt.strftime("%m-%d")
            except ValueError:
                label = ds
            pa_x_label_parts.append(
                f'<text x="{_x(i):.1f}" y="{PAD_T + chart_h + 18}" text-anchor="middle" '
                f'fill="var(--muted)" font-size="10" font-family="JetBrains Mono, monospace">{label}</text>'
            )

    pa_axis_el = (
        f'<line x1="{PAD_L}" y1="{PAD_T + chart_h}" x2="{PAD_L + chart_w}" y2="{PAD_T + chart_h}" '
        f'stroke="var(--border)" stroke-width="1"/>'
    )

    pa_line_parts = []
    pa_legend_parts = []
    for author_name, total in author_commit_totals:
        dc = per_author_daily.get(author_name, {})
        series = [(ds, int(dc.get(ds, 0))) for ds in all_dates]
        color = color_map.get(author_name, "#58a6ff")
        # Polyline across the window. Two overlaid polylines: a wide, fully
        # transparent "hit" line makes the line easy to hover-target (SVG
        # stroke hit-testing ignores fill but respects stroke-width), and the
        # visible line carries the same <title> so hovering anywhere along
        # the curve shows the author tooltip — not just on data points.
        if n >= 2:
            pts = " ".join(f"{_x(i):.1f},{_pa_y(v):.1f}" for i, (_, v) in enumerate(series))
            line_tip = f"{author_name} · 共 {total} 次提交"
            pa_line_parts.append(
                f'<polyline class="pa-hit" points="{pts}" fill="none" stroke="transparent" '
                f'stroke-width="12" stroke-linejoin="round" stroke-linecap="round" pointer-events="stroke">'
                f'<title>{line_tip}</title></polyline>'
                f'<polyline class="pa-line" data-author="{author_name}" points="{pts}" fill="none" '
                f'stroke="{color}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" '
                f'opacity="0.85" pointer-events="stroke">'
                f'<title>{line_tip}</title></polyline>'
            )
        # Data-point circles only where the author actually committed, to keep
        # the chart legible even with many overlapping authors.
        for i, (ds, v) in enumerate(series):
            if v <= 0:
                continue
            try:
                dt = datetime.strptime(ds, "%Y-%m-%d")
                weekdays = ["一", "二", "三", "四", "五", "六", "日"]
                tip = f"{author_name} · {dt.strftime('%Y-%m-%d')} 周{weekdays[dt.weekday()]} · {v} 次"
            except ValueError:
                tip = f"{author_name} · {ds} · {v} 次"
            pa_line_parts.append(
                f'<circle class="pa-pt" cx="{_x(i):.1f}" cy="{_pa_y(v):.1f}" r="2.5" '
                f'fill="var(--bg)" stroke="{color}" stroke-width="1.6">'
                f'<title>{tip}</title></circle>'
            )
        pa_legend_parts.append(
            f'<span class="pa-legend-item">'
            f'<span class="pa-swatch" style="background:{color}"></span>'
            f'<span class="pa-legend-name">{author_name}</span>'
            f'<span class="pa-legend-total mono">{total}</span>'
            f'</span>'
        )

    pa_empty_el = ""
    if not author_commit_totals:
        pa_empty_el = (
            f'<text x="{SVG_W / 2}" y="{PAD_T + chart_h / 2}" text-anchor="middle" '
            f'fill="var(--muted-2)" font-size="12">（该时段无作者提交）</text>'
        )

    if author_commit_totals:
        per_author_html = f'''
  <div class="section">
    <h2>每人提交趋势</h2>
    <p class="note">与上图共享同一时间轴与提交次数 Y 轴，每位作者一条独立折线；悬停数据点查看作者与提交数，图例按窗口内总提交数降序排列。</p>
    <div class="chart-container">
      <svg viewBox="0 0 {SVG_W} {SVG_H}" preserveAspectRatio="none" width="100%" height="{SVG_H}"
           role="img" aria-label="每人每日提交次数折线图">
        {"".join(pa_grid_parts)}
        {"".join(pa_line_parts)}
        {pa_axis_el}
        {"".join(pa_x_label_parts)}
        {pa_empty_el}
      </svg>
      <div class="pa-legend">{"".join(pa_legend_parts)}</div>
    </div>
  </div>'''
    else:
        per_author_html = ""

    # Each cell in the daily breakdown shows the NET added lines for that
    # (author, date): ins - del. Zero means no activity that day. The `title`
    # attribute exposes the ins/del breakdown on hover so readers can see the
    # churn behind the net number.
    def _cell_tip(ins: int, del_: int, net: int) -> str:
        return f"新增 +{ins:,} / 删除 -{del_:,} / 净增加 {'+' if net >= 0 else ''}{net:,}"

    daily_table_rows = ""
    for a in sorted_authors:
        avatar = f'<span class="avatar" style="background:{color_map[a]}">{a[0]}</span>'
        cells = ""
        row_ins = row_del = row_total = 0
        for date_str in all_dates:
            v = daily_data.get(date_str, {}).get(a, {})
            ins = v.get("ins", 0)
            dl = v.get("del", 0)
            net = ins - dl
            row_ins += ins
            row_del += dl
            row_total += net
            tip = _cell_tip(ins, dl, net)
            if ins == 0 and dl == 0:
                cells += f'<td title="当日无提交">-</td>'
            elif net == 0:
                cells += f'<td class="num" title="{tip}" style="color:var(--muted)">0</td>'
            else:
                color = 'var(--pos)' if net > 0 else 'var(--neg)'
                sign = "+" if net > 0 else ""
                cells += f'<td class="num" title="{tip}" style="color:{color}">{sign}{net}</td>'
        row_sign = "+" if row_total > 0 else ""
        row_color = 'var(--pos)' if row_total > 0 else ('var(--neg)' if row_total < 0 else 'var(--muted)')
        row_tip = _cell_tip(row_ins, row_del, row_total)
        daily_table_rows += (
            f'<tr><td>{avatar}{a}</td>{cells}'
            f'<td title="{row_tip}"><strong style="color:{row_color}">{row_sign}{row_total:,}</strong></td></tr>\n'
        )

    total_row_cells = ""
    grand_ins = grand_del = grand_total = 0
    for date_str in all_dates:
        day_ins = sum(v.get("ins", 0) for v in daily_data.get(date_str, {}).values())
        day_del = sum(v.get("del", 0) for v in daily_data.get(date_str, {}).values())
        day_total = day_ins - day_del
        grand_ins += day_ins
        grand_del += day_del
        grand_total += day_total
        sign = "+" if day_total > 0 else ""
        color = 'var(--pos)' if day_total > 0 else ('var(--neg)' if day_total < 0 else 'var(--muted)')
        tip = _cell_tip(day_ins, day_del, day_total)
        total_row_cells += f'<td title="{tip}" style="color:{color}">{sign}{day_total:,}</td>'
    g_sign = "+" if grand_total > 0 else ""
    g_color = 'var(--pos)' if grand_total > 0 else ('var(--neg)' if grand_total < 0 else 'var(--muted)')
    g_tip = _cell_tip(grand_ins, grand_del, grand_total)
    daily_table_total = (
        f'<tr style="background:var(--panel-2);font-weight:700">'
        f'<td>合计</td>{total_row_cells}'
        f'<td title="{g_tip}" style="color:{g_color}">{g_sign}{grand_total:,}</td></tr>'
    )

    date_headers = "".join(f'<th>{fmt_date(d)}</th>' for d in all_dates)

    raw_table_rows = ""
    for a in sorted_authors:
        s = authors[a]
        avatar = f'<span class="avatar" style="background:{color_map[a]}">{a[0]}</span>'
        raw_net_a = s["raw_ins"] - s["raw_del"]
        net_sign = "+" if raw_net_a >= 0 else ""
        raw_table_rows += f'''<tr>
            <td>{avatar}{a}</td>
            <td>{s["raw_commits"]}</td>
            <td style="color:#3fb950">{s["raw_ins"]:,}</td>
            <td style="color:#f85149">{s["raw_del"]:,}</td>
            <td class="{'pos' if raw_net_a >= 0 else 'neg'}">{net_sign}{raw_net_a:,}</td>
        </tr>\n'''

    eff_table_rows = ""
    max_net = max((a["eff_ins"] - a["eff_del"] for a in authors.values()), default=1)
    for a in sorted_authors:
        s = authors[a]
        avatar = f'<span class="avatar" style="background:{color_map[a]}">{a[0]}</span>'
        net = s["eff_ins"] - s["eff_del"]
        net_sign = "+" if net >= 0 else ""
        pct = abs(net) / max(max_net, 1) * 100
        green_pct = (s["eff_ins"] / max(s["eff_ins"] + s["eff_del"], 1)) * 100 if (s["eff_ins"] + s["eff_del"]) > 0 else 100
        eff_table_rows += f'''<tr>
            <td>{avatar}<strong>{a}</strong></td>
            <td>{s.get("eff_files", 0)}</td>
            <td style="color:var(--pos)">{s["eff_ins"]:,}</td>
            <td style="color:var(--neg)">{s["eff_del"]:,}</td>
            <td class="bar-cell"><div class="bar" style="width:{pct:.1f}%;background:linear-gradient(90deg,var(--pos) {green_pct:.0f}%,var(--neg) {green_pct:.0f}% 100%)"><span class="bar-text">{net_sign}{net:,}</span></div></td>
        </tr>\n'''

    filter_del_pct = f"-{(1 - eff_del / raw_del) * 100:.1f}%" if raw_del > 0 else "N/A"
    filter_net_pct = f"-{abs(1 - abs(eff_net) / max(abs(raw_net), 1)) * 100:.1f}%" if raw_net != 0 else "N/A"

    repos_list = ", ".join(d.get("repo_names", []))

    def _esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def _fmt_commit_time(iso: str) -> str:
        try:
            dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return iso or ""

    repos_meta = d.get("repos_meta", []) or []
    if repos_meta:
        repos_meta_rows = ""
        for rm in repos_meta:
            name = _esc(rm.get("name", ""))
            url = rm.get("url")
            name_cell = f'<a href="{_esc(url)}" target="_blank" rel="noopener">{name}</a>' if url else name
            lc = rm.get("last_commit")
            if lc:
                short = _esc(lc.get("short", ""))
                full = _esc(lc.get("hash", ""))
                subject = _esc(lc.get("subject", ""))
                time_str = _fmt_commit_time(lc.get("iso_date", ""))
                if url and full:
                    commit_cell = f'<a href="{_esc(url)}/commit/{full}" target="_blank" rel="noopener" title="{subject}"><code>{short}</code></a>'
                else:
                    commit_cell = f'<code title="{subject}">{short}</code>' if short else "—"
                time_cell = _esc(time_str)
            else:
                commit_cell = "—"
                time_cell = "—"
            repos_meta_rows += f'<tr><td>{name_cell}</td><td>{rm.get("commits", 0)}</td><td>{commit_cell}</td><td>{time_cell}</td></tr>\n'
        repos_meta_html = f'''
  <div class="section">
    <h2>仓库清单（{len(repos_meta)}）</h2>
    <div class="chart-container" style="padding:16px 20px">
      <table>
        <thead><tr><th>仓库</th><th>窗口内提交数</th><th>最后提交</th><th>提交时间</th></tr></thead>
        <tbody>
          {repos_meta_rows}
        </tbody>
      </table>
    </div>
  </div>'''
    else:
        repos_meta_html = ""

    # Contribution reviews section (optional, rendered only when --reviews-json is supplied).
    review_html = ""
    reviews_payload = d.get("reviews")
    if isinstance(reviews_payload, dict) and reviews_payload.get("reviews"):
        COMPLEXITY_LABEL = {"high": "高复杂度", "medium": "中复杂度", "low": "低复杂度"}
        cards_html = []
        # Order by total score desc so top performers float up; fall back to author name.
        rv_items = sorted(
            reviews_payload["reviews"],
            key=lambda r: (-float(r.get("total") or 0), str(r.get("author", ""))),
        )
        for rv in rv_items:
            author = str(rv.get("author", "?"))
            color = color_map.get(author, get_color(author))
            scores = rv.get("scores") or {}
            try:
                total = float(rv.get("total") if rv.get("total") is not None
                              else (scores.get("output", 0) * 0.2 + scores.get("quality", 0) * 0.3
                                    + scores.get("impact", 0) * 0.3 + scores.get("collab", 0) * 0.2))
            except Exception:
                total = 0.0
            summary = _esc(str(rv.get("summary", "") or ""))
            long_term = _esc(str(rv.get("long_term", "") or ""))
            quality_info = rv.get("quality") or {}
            q_issues = _esc(str(quality_info.get("issues", "") or ""))
            q_rework = _esc(str(quality_info.get("rework", "") or ""))

            def _score_bar(label: str, key: str) -> str:
                v = scores.get(key)
                try:
                    vf = max(0.0, min(100.0, float(v)))
                except Exception:
                    vf = 0.0
                return (f'<div class="score-item"><span class="sl">{label}</span>'
                        f'<span class="sv">{vf:.0f}</span>'
                        f'<span class="sbar"><i style="width:{vf:.0f}%;background:{color}"></i></span></div>')

            works_lis = []
            for w in (rv.get("works") or []):
                title = _esc(str(w.get("title", "") or ""))
                cx = str(w.get("complexity", "medium") or "medium").lower()
                cx_label = COMPLEXITY_LABEL.get(cx, cx)
                business = _esc(str(w.get("business", "") or ""))
                risk = _esc(str(w.get("risk", "") or ""))
                ev_chips = []
                for ev in (w.get("evidence") or []):
                    if isinstance(ev, dict):
                        sha = _esc(str(ev.get("sha", "") or ""))
                        note = _esc(str(ev.get("note", "") or ""))
                        ev_chips.append(f'<code title="{note}">{sha}</code>' if note else f'<code>{sha}</code>')
                    else:
                        ev_chips.append(f'<code>{_esc(str(ev))}</code>')
                ev_html = (" ".join(ev_chips)) if ev_chips else '<span class="muted">—</span>'
                details = []
                if business:
                    details.append(f'<div><strong>业务：</strong>{business}</div>')
                if risk:
                    details.append(f'<div><strong>风险：</strong>{risk}</div>')
                details.append(f'<div class="evidence"><strong>证据：</strong>{ev_html}</div>')
                works_lis.append(
                    f'<li><div class="work-head"><span class="work-title">{title}</span>'
                    f'<span class="tag tag-{cx}">{cx_label}</span></div>'
                    f'<div class="work-body">{"".join(details)}</div></li>'
                )
            works_html = ("<ol>" + "".join(works_lis) + "</ol>") if works_lis else ""

            quality_html = ""
            if q_issues or q_rework:
                bits = []
                if q_issues:
                    bits.append(f'<div><strong>问题：</strong>{q_issues}</div>')
                if q_rework:
                    bits.append(f'<div><strong>返工：</strong>{q_rework}</div>')
                quality_html = (
                    f'<div class="rv-block"><h3>质量与返工</h3>{"".join(bits)}</div>'
                )

            cards_html.append(f'''
      <article class="review-card" style="--rv-accent:{color}">
        <header class="rv-head">
          <div class="rv-id">
            <div class="rv-name">{_esc(author)}</div>
            <div class="rv-meta">{len(rv.get("works") or [])} 项工作 · 加权总分</div>
          </div>
          <div class="rv-total"><b>{total:.0f}</b><span>/100</span></div>
        </header>
        <div class="score-grid">
          {_score_bar("产出 20%", "output")}
          {_score_bar("质量 30%", "quality")}
          {_score_bar("影响 30%", "impact")}
          {_score_bar("协作长期 20%", "collab")}
        </div>
        {f'<div class="rv-summary">{summary}</div>' if summary else ''}
        {f'<div class="rv-block"><h3>本期工作</h3>{works_html}</div>' if works_html else ''}
        {quality_html}
        {f'<div class="rv-block"><h3>长期价值</h3><p>{long_term}</p></div>' if long_term else ''}
      </article>''')

        rubric_text = _esc(str((reviews_payload.get("rubric") or {}).get("formula",
                            "总分 = 产出×20% + 质量×30% + 影响×30% + 协作与长期价值×20%")))
        review_html = f'''
  <div class="section">
    <h2>贡献点评</h2>
    <p class="note">{rubric_text}（每项 0-100）。评语由 LLM 基于本期 commit 元数据生成，供团队参考。</p>
    <div class="reviews">{"".join(cards_html)}
    </div>
  </div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{period_label} 代码报告</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0b0f14;
    --panel: #11161d;
    --panel-2: #161c25;
    --hover: #1a2130;
    --border: #1f2630;
    --border-soft: #161c25;
    --text: #e6edf3;
    --text-2: #c9d1d9;
    --muted: #7d8590;
    --muted-2: #545d6a;
    --accent: #58a6ff;
    --pos: #3fb950;
    --neg: #f85149;
    --warn: #d29922;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html {{ -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    background-image: radial-gradient(circle at 20% -10%, rgba(88,166,255,0.06) 0%, transparent 40%),
                      radial-gradient(circle at 100% 0%, rgba(63,185,80,0.04) 0%, transparent 45%);
    color: var(--text-2);
    padding: 48px 32px 64px;
    font-size: 14px;
    line-height: 1.5;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .num, code, .mono {{ font-family: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace; font-variant-numeric: tabular-nums; }}
  table td, table th {{ font-variant-numeric: tabular-nums; }}

  header {{ margin-bottom: 40px; }}
  .eyebrow {{ display: inline-block; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; color: var(--accent); font-weight: 600; margin-bottom: 10px; }}
  h1 {{ font-size: 32px; line-height: 1.15; letter-spacing: -0.02em; font-weight: 700; color: var(--text); margin-bottom: 12px; }}
  .subtitle {{ color: var(--muted); font-size: 14px; }}
  .subtitle .dot {{ color: var(--muted-2); margin: 0 8px; }}
  .method {{ color: var(--muted-2); font-size: 12px; margin-top: 14px; }}
  .method code {{ background: var(--panel-2); padding: 2px 6px; border-radius: 4px; color: var(--accent); font-size: 11px; border: 1px solid var(--border); }}

  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 40px; }}
  .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 20px 22px; position: relative; overflow: hidden; transition: border-color .15s ease; }}
  .card:hover {{ border-color: #2a3340; }}
  .card::before {{ content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--accent); opacity: 0.5; }}
  .card.pos::before {{ background: var(--pos); }}
  .card.neg::before {{ background: var(--neg); }}
  .card .label {{ font-size: 11px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px; font-weight: 500; }}
  .card .value {{ font-size: 30px; font-weight: 700; color: var(--text); letter-spacing: -0.02em; font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
  .card .sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}

  h2 {{ font-size: 15px; color: var(--text); margin-bottom: 12px; font-weight: 600; letter-spacing: -0.01em; display: flex; align-items: center; gap: 10px; }}
  h2::before {{ content: ""; width: 3px; height: 14px; background: var(--accent); border-radius: 2px; }}
  .section {{ margin-bottom: 40px; }}
  .note {{ font-size: 12px; color: var(--muted); margin-bottom: 14px; line-height: 1.7; }}
  .note strong {{ color: var(--text-2); font-weight: 600; }}
  td[title], th[title] {{ cursor: help; }}

  table {{ width: 100%; border-collapse: separate; border-spacing: 0; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; font-size: 13px; }}
  th {{ background: var(--panel-2); padding: 12px 16px; text-align: left; font-size: 11px; color: var(--muted); letter-spacing: 0.8px; text-transform: uppercase; font-weight: 600; border-bottom: 1px solid var(--border); }}
  td {{ padding: 12px 16px; border-top: 1px solid var(--border-soft); color: var(--text-2); }}
  tbody tr:first-child td {{ border-top: none; }}
  tbody tr {{ transition: background .12s ease; }}
  tbody tr:hover td {{ background: var(--hover); }}

  .bar-cell {{ position: relative; }}
  .bar {{ height: 22px; border-radius: 4px; min-width: 3px; }}
  .bar-text {{ position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 11px; font-weight: 600; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.5); white-space: nowrap; font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }}
  .avatar {{ width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 600; font-size: 11px; color: #fff; margin-right: 10px; vertical-align: middle; letter-spacing: 0; }}

  .chart-container {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px 16px; }}
  .chart-container svg {{ display: block; width: 100%; height: auto; overflow: visible; }}
  .chart-container svg .pt {{ transition: r .12s ease, stroke-width .12s ease; cursor: crosshair; }}
  .chart-container svg .pt:hover {{ r: 5; stroke-width: 3; }}
  .chart-summary {{ display: flex; flex-wrap: wrap; gap: 24px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border-soft); font-size: 12px; color: var(--muted); }}
  .chart-summary .label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted-2); margin-right: 4px; }}
  .chart-summary strong {{ color: var(--text); font-weight: 600; }}

  .pa-legend {{ display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border-soft); font-size: 12px; color: var(--muted); }}
  .pa-legend-item {{ display: inline-flex; align-items: center; gap: 6px; transition: opacity .15s ease; }}
  .pa-swatch {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .pa-legend-name {{ color: var(--text-2); }}
  .pa-legend-total {{ color: var(--muted); font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; font-size: 11px; }}
  .pa-pt {{ transition: r .12s ease, stroke-width .12s ease; cursor: crosshair; }}
  .pa-pt:hover {{ r: 4; stroke-width: 2.4; }}
  .pa-line {{ transition: opacity .12s ease, stroke-width .12s ease; cursor: crosshair; }}
  .pa-hit {{ cursor: crosshair; }}
  .pa-hit:hover + .pa-line, .pa-line:hover {{ opacity: 1; stroke-width: 2.4; }}

  .pos {{ color: var(--pos); font-weight: 600; }}
  .neg {{ color: var(--neg); font-weight: 600; }}
  .num {{ font-weight: 500; }}

  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 40px; }}
  .grid2 > .section {{ margin-bottom: 0; }}
  @media (max-width: 860px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}

  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  code {{ background: var(--panel-2); padding: 2px 6px; border-radius: 4px; font-size: 12px; color: var(--accent); border: 1px solid var(--border); }}

  footer {{ text-align: center; color: var(--muted-2); font-size: 11px; margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--border-soft); }}
  footer code {{ background: transparent; border: none; padding: 0; color: var(--muted); }}
  .scroll-wrap {{ overflow-x: auto; }}

  /* === Contribution reviews === */
  .reviews {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }}
  .review-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px 22px; position: relative; overflow: hidden;
    border-left: 3px solid var(--rv-accent, var(--accent)); }}
  .rv-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
    padding-bottom: 14px; border-bottom: 1px solid var(--border-soft); margin-bottom: 14px; }}
  .rv-name {{ font-size: 18px; font-weight: 600; color: var(--text); }}
  .rv-meta {{ font-size: 11px; color: var(--muted-2); margin-top: 2px; letter-spacing: 0.02em; }}
  .rv-total {{ font-family: 'JetBrains Mono', monospace; display: flex; align-items: baseline; gap: 2px;
    color: var(--rv-accent, var(--accent)); }}
  .rv-total b {{ font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .rv-total span {{ font-size: 12px; color: var(--muted); }}
  .score-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; margin-bottom: 14px; }}
  .score-item {{ display: grid; grid-template-columns: auto auto 1fr; gap: 8px; align-items: center;
    font-size: 12px; }}
  .score-item .sl {{ color: var(--muted); }}
  .score-item .sv {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; color: var(--text);
    font-variant-numeric: tabular-nums; min-width: 28px; text-align: right; }}
  .score-item .sbar {{ height: 6px; background: var(--panel-2); border-radius: 3px; overflow: hidden; }}
  .score-item .sbar i {{ display: block; height: 100%; border-radius: 3px; }}
  .rv-summary {{ font-size: 13px; color: var(--muted); line-height: 1.65; margin-bottom: 14px;
    padding: 10px 12px; background: var(--panel-2); border-radius: 6px; border-left: 2px solid var(--rv-accent, var(--accent)); }}
  .rv-block {{ margin-top: 12px; }}
  .rv-block h3 {{ font-size: 12px; font-weight: 600; color: var(--muted-2); text-transform: uppercase;
    letter-spacing: 0.08em; margin: 0 0 8px; }}
  .rv-block ol {{ margin: 0; padding-left: 20px; display: grid; gap: 10px; }}
  .rv-block li {{ font-size: 13px; color: var(--text); line-height: 1.6; }}
  .work-head {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }}
  .work-title {{ font-weight: 500; }}
  .work-body {{ font-size: 12px; color: var(--muted); display: grid; gap: 2px; padding: 4px 0; }}
  .work-body strong {{ color: var(--muted-2); font-weight: 500; }}
  .evidence code {{ font-size: 11px; padding: 1px 5px; margin-right: 2px; }}
  .tag {{ display: inline-block; font-size: 10px; padding: 2px 7px; border-radius: 10px;
    font-weight: 500; letter-spacing: 0.02em; border: 1px solid transparent; }}
  .tag-high   {{ background: rgba(248,81,73,0.12);  color: #f85149; border-color: rgba(248,81,73,0.25); }}
  .tag-medium {{ background: rgba(210,153,34,0.12); color: #d29922; border-color: rgba(210,153,34,0.25); }}
  .tag-low    {{ background: rgba(63,185,80,0.12);  color: #3fb950; border-color: rgba(63,185,80,0.25); }}
  .muted {{ color: var(--muted); }}
</style>
</head>
<body>
<div class="container">
  <header>
    <span class="eyebrow">Code Report · {period_label}</span>
    <h1>{period_label}代码报告</h1>
    <p class="subtitle">
      <span class="mono">{repos_count}</span> 仓库<span class="dot">·</span>全部分支<span class="dot">·</span><span class="mono">{since_label} — {until_label}</span>
    </p>
    <p class="method">
      原始 = 全部文件 · <code>git log --shortstat</code> &nbsp; 有效代码 = 仅代码文件，已剔除注释和空行
    </p>
  </header>

  <div class="cards">
    <div class="card"><div class="label">总提交数</div><div class="value">{total_commits:,}</div><div class="sub">全部作者</div></div>
    <div class="card"><div class="label">原始行数</div><div class="value">+{raw_ins:,}</div><div class="sub">删除 {raw_del:,}</div></div>
    <div class="card pos"><div class="label">有效代码行</div><div class="value">+{eff_ins:,}</div><div class="sub">删除 {eff_del:,}</div></div>
    <div class="card {'pos' if eff_net >= 0 else 'neg'}"><div class="label">净增有效代码</div><div class="value" style="color:{'var(--pos)' if eff_net >= 0 else 'var(--neg)'}">{'+' if eff_net >= 0 else ''}{eff_net:,}</div><div class="sub">仅代码</div></div>
  </div>
{review_html}
  <div class="section">
    <h2>每日代码提交趋势</h2>
    <p class="note">Y 轴 = 当日提交次数（<span class="mono">git log --no-merges</span> 聚合所有仓库和作者）。悬停任意数据点可查看具体数值与星期。</p>
    <div class="chart-container">
      {commit_chart_svg}
      {commit_chart_summary}
    </div>
  </div>
{per_author_html}

  <div class="grid2">
    <div class="section">
      <h2>原始行数（全部文件）</h2>
      <table>
        <thead><tr><th>作者</th><th>提交数</th><th>新增</th><th>删除</th><th>净增</th></tr></thead>
        <tbody>{raw_table_rows}</tbody>
      </table>
    </div>

    <div class="section">
      <h2>有效代码（剔除注释/空行）</h2>
      <table>
        <thead><tr><th>作者</th><th>文件数</th><th>新增</th><th>删除</th><th style="width:30%">净增</th></tr></thead>
        <tbody>{eff_table_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <h2>每日明细</h2>
    <p class="note">
      单元格数值 = <strong>净增加行数</strong>（当日新增 − 当日删除）。
      <span class="pos">绿色</span> 表示净增，<span class="neg">红色</span> 表示净减，
      <span style="color:var(--muted)">0</span> 表示有提交但增删相抵，<span style="color:var(--muted)">-</span> 表示当日无提交。
      鼠标悬停任意单元格可查看 <span class="mono">新增 / 删除 / 净增</span> 拆分。
    </p>
    <div class="scroll-wrap">
    <table>
      <thead><tr><th>作者</th>{date_headers}<th>合计</th></tr></thead>
      <tbody>
        {daily_table_rows}
        {daily_table_total}
      </tbody>
    </table>
    </div>
  </div>

  <div class="section">
    <h2>过滤效果对比</h2>
    <div class="chart-container" style="padding:16px 20px">
      <table style="border:none;background:transparent">
        <thead><tr><th style="background:transparent">指标</th><th style="background:transparent">原始（全部文件）</th><th style="background:transparent">有效代码</th><th style="background:transparent">过滤掉</th></tr></thead>
        <tbody>
          <tr><td style="border:none">新增行</td><td style="border:none">{raw_ins:,}</td><td style="border:none;color:#3fb950;font-weight:700">{eff_ins:,}</td><td style="border:none;color:#f85149">{filter_pct}</td></tr>
          <tr><td style="border:none">删除行</td><td style="border:none">{raw_del:,}</td><td style="border:none;color:#f85149;font-weight:700">{eff_del:,}</td><td style="border:none;color:#f85149">{filter_del_pct}</td></tr>
          <tr><td style="border:none">净增</td><td style="border:none">{'+' if raw_net >= 0 else ''}{raw_net:,}</td><td style="border:none;color:{'#3fb950' if eff_net >= 0 else '#f85150'};font-weight:700">{'+' if eff_net >= 0 else ''}{eff_net:,}</td><td style="border:none;color:#f85149">{filter_net_pct}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
{repos_meta_html}
  <footer>生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} &middot; scripts/codereport.py &middot; 统计周期：{since_label} ~ {until_label}</footer>
</div>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved to: {output_path}", file=sys.stderr)


def merge_authors(all_raw: Dict[str, Dict], all_eff: Dict[str, Dict],
                  all_daily: Dict[str, Dict]) -> Dict[str, dict]:
    authors = defaultdict(lambda: {
        "raw_commits": 0, "raw_ins": 0, "raw_del": 0,
        "eff_ins": 0, "eff_del": 0, "eff_files": 0
    })
    for repo_stats in all_raw.values():
        for a, s in repo_stats.items():
            authors[a]["raw_commits"] += s["commits"]
            authors[a]["raw_ins"] += s["ins"]
            authors[a]["raw_del"] += s["del"]
    for repo_stats in all_eff.values():
        for a, s in repo_stats.items():
            authors[a]["eff_ins"] += s["ins"]
            authors[a]["eff_del"] += s["del"]
            authors[a]["eff_files"] += s["files"]
    return dict(authors)


def merge_daily(all_daily_lines: Dict[str, Dict[str, Dict]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    merged = defaultdict(lambda: defaultdict(lambda: {"ins": 0, "del": 0}))
    for repo_daily in all_daily_lines.values():
        for date, authors in repo_daily.items():
            for author, stats in authors.items():
                merged[date][author]["ins"] += stats["ins"]
                merged[date][author]["del"] += stats["del"]
    return {d: dict(a) for d, a in merged.items()}


def main():
    parser = argparse.ArgumentParser(description="Multi-repo git contributor HTML report")
    parser.add_argument("--dir", default=".", help="Root directory containing git repos (default: current)")
    parser.add_argument("--since", required=True, help="Start date, e.g. '7 days ago' or '2026-04-07'")
    parser.add_argument("--until", default="now", help="End date (default: now)")
    parser.add_argument("--output", default="", help="Output HTML file path")
    parser.add_argument("--skip-eff", action="store_true", help="Skip effective code analysis (faster)")
    parser.add_argument("--repos", default="", help="Comma-separated repo names to include (default: all)")
    parser.add_argument("--authors-config", default=DEFAULT_AUTHORS_CONFIG,
                        help=f"Path to authors JSON config (default: {DEFAULT_AUTHORS_CONFIG}). "
                             "Aliases are loaded from this file; newly-seen authors/emails are appended.")
    parser.add_argument("--no-update-authors", action="store_true",
                        help="Do not write newly-discovered authors back to the config file.")
    parser.add_argument("--dump-commits", default="",
                        help="Write per-author commit metadata (sha/message/files/numstat) to this JSON path, "
                             "then exit. The agent uses this dump to generate reviews.")
    parser.add_argument("--reviews-json", default="",
                        help="Path to LLM-generated reviews JSON. When provided, the report gains a "
                             "'贡献点评' section rendered before the daily commit trend chart.")
    args = parser.parse_args()

    authors_config = load_authors_config(args.authors_config)
    print(f"Loaded {len(AUTHOR_ALIASES)} alias mappings from {args.authors_config}"
          if AUTHOR_ALIASES else f"No alias config at {args.authors_config} (will create on first write)",
          file=sys.stderr)

    root = os.path.abspath(args.dir)
    print(f"Scanning for git repos in: {root}", file=sys.stderr)
    repos = find_repos(root)
    print(f"Found {len(repos)} repos", file=sys.stderr)

    if args.repos:
        repo_names = set(r.strip() for r in args.repos.split(","))
        repos = [r for r in repos if os.path.basename(r) in repo_names]
        print(f"Filtered to {len(repos)} repos: {', '.join(os.path.basename(r) for r in repos)}", file=sys.stderr)

    since = args.since
    until = args.until

    since_dt = None
    until_dt = None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            since_dt = datetime.strptime(since, fmt)
            break
        except ValueError:
            pass
    if since_dt is None:
        try:
            result = subprocess.run(["date", "-j", "-f", "%Y-%m-%d", since, "+%Y-%m-%d"],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                since_dt = datetime.strptime(result.stdout.strip(), "%Y-%m-%d")
        except Exception:
            pass
    if since_dt is None:
        since_dt = datetime.now() - timedelta(days=7)
    until_dt = datetime.now()

    try:
        raw_since = run(["git", "log", "-1", "--format=%ai", f"--before={until}", f"--after={since}"],
                        cwd=repos[0] if repos else ".").strip().split()[0] if repos else since
    except Exception:
        raw_since = since

    if "day" in since.lower() or "week" in since.lower() or "month" in since.lower():
        since_label = since
    else:
        since_label = since

    since_label = since_dt.strftime("%Y-%m-%d") if since_dt else since
    until_label = until_dt.strftime("%Y-%m-%d")

    diff_days = (until_dt - since_dt).days if since_dt and until_dt else 7
    if diff_days <= 7:
        period_label = "周"
    elif diff_days <= 31:
        period_label = "月"
    else:
        period_label = ""

    all_raw = {}
    all_eff = {}
    all_daily_lines = {}
    all_daily_commits: Dict[str, Dict[str, Dict[str, int]]] = {}
    total_commits = 0
    repo_names = []
    repos_meta: List[dict] = []
    all_seen: Dict[str, Set[str]] = defaultdict(set)
    dump_by_author: Dict[str, List[dict]] = defaultdict(list) if args.dump_commits else {}

    for i, repo in enumerate(repos):
        name = os.path.basename(repo)
        print(f"[{i + 1}/{len(repos)}] {name} ...", file=sys.stderr, end=" ")

        try:
            n = get_total_commits(repo, since, until)
            if n == 0:
                print("0 commits, skipped", file=sys.stderr)
                continue
            total_commits += n
            repo_names.append(name)
            print(f"{n} commits", file=sys.stderr)

            repos_meta.append({
                "name": name,
                "url": get_repo_remote_url(repo),
                "last_commit": get_last_commit_in_window(repo, since, until),
                "commits": n,
            })

            for raw_name, emails in collect_author_identities(repo, since, until).items():
                all_seen[raw_name].update(emails)

            raw = get_raw_stats(repo, since, until)
            if raw:
                all_raw[repo] = raw
                all_daily_lines[repo] = get_daily_lines(repo, since, until)
                all_daily_commits[repo] = get_daily_commits(repo, since, until)

            if not args.skip_eff:
                eff = get_effective_stats(repo, since, until)
                if eff:
                    all_eff[repo] = eff

            if args.dump_commits:
                repo_url = get_repo_remote_url(repo)
                for c in get_author_commits(repo, since, until):
                    c["repo"] = name
                    c["repo_url"] = repo_url
                    dump_by_author[c["author"]].append(c)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            continue

    if not all_raw and not all_eff:
        print("No data found in any repo for the given period.", file=sys.stderr)
        sys.exit(1)

    if args.dump_commits:
        dump_payload = {
            "window": {"since": since_label, "until": until_label},
            "rubric": {
                "formula": "总分 = 产出×20% + 质量×30% + 影响×30% + 协作与长期价值×20%",
                "scale": "每项 0-100",
                "dimensions": ["output", "quality", "impact", "collab"],
            },
            "authors": {
                author: {
                    "total_commits": len(commits),
                    "total_insertions": sum(c["insertions"] for c in commits),
                    "total_deletions": sum(c["deletions"] for c in commits),
                    "repos": sorted({c["repo"] for c in commits}),
                    "commits": sorted(commits, key=lambda c: c["date"]),
                }
                for author, commits in dump_by_author.items()
            },
        }
        with open(args.dump_commits, "w", encoding="utf-8") as f:
            json.dump(dump_payload, f, ensure_ascii=False, indent=2)
        print(f"Commit dump saved to: {args.dump_commits} "
              f"({sum(len(v) for v in dump_by_author.values())} commits across "
              f"{len(dump_by_author)} authors)", file=sys.stderr)
        return

    print("Merging data...", file=sys.stderr)
    authors = merge_authors(all_raw, all_eff, all_daily_lines)
    daily_lines = merge_daily(all_daily_lines)

    today = datetime.now().strftime("%Y-%m-%d")
    if args.output:
        output_path = args.output
    else:
        output_path = os.path.join(tempfile.gettempdir(), f"code-report-{today}.html")

    reviews_data = None
    if args.reviews_json:
        try:
            with open(args.reviews_json, "r", encoding="utf-8") as f:
                reviews_data = json.load(f)
            n = len(reviews_data.get("reviews", [])) if isinstance(reviews_data, dict) else 0
            print(f"Loaded {n} contributor reviews from {args.reviews_json}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: failed to load reviews from {args.reviews_json}: {e}", file=sys.stderr)
            reviews_data = None

    report_data = {
        "authors": authors,
        "total_commits": total_commits,
        "repos_count": len(repo_names),
        "repo_names": repo_names,
        "since": since_label,
        "until": until_label,
        "period_label": period_label,
        "daily_lines": daily_lines,
        "daily_commits": merge_daily_commit_totals(all_daily_commits),
        "per_author_daily": merge_per_author_daily_commits(all_daily_commits),
        "repos_meta": repos_meta,
        "reviews": reviews_data,
    }

    generate_html(report_data, output_path)

    if not args.no_update_authors and all_seen:
        added = update_authors_config(args.authors_config, authors_config, all_seen)
        if added:
            print(f"Updated {args.authors_config}: +{added} author/email entries. "
                  "Edit the file to merge duplicates (set shared 'canonical' and move names into 'aliases').",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
