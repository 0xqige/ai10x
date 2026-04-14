---
name: code-report
description: Use when user asks for git contributor stats, code report, team productivity analysis, weekly/monthly dev report, or comparing raw vs effective code changes across single or multiple git repositories.
---

# Code Report - Multi-Repo Git Contributor Analysis

## Overview

Generate HTML reports analyzing git contributor statistics across one or more repositories. Reports show raw lines, effective code (excluding comments/blank lines), commit trends, daily breakdowns, and filter comparisons.

## When to Use

- "Generate a weekly code report"
- "Show team contribution stats for last month"
- "Compare raw vs effective code for debox repos"
- "Who wrote the most code this week?"

## Script Location

The analyzer script lives **inside this skill**:

```
${SKILL_DIR}/scripts/codereport.py
```

`${SKILL_DIR}` is this skill's directory (the folder containing this SKILL.md). Always invoke the bundled script via its absolute path so it works regardless of the user's current working directory:

```bash
python3 "${SKILL_DIR}/scripts/codereport.py" [options]
```

## Quick Reference

| Flag | Description |
|------|-------------|
| `--since "7 days ago"` | Start of analysis window (git log syntax or ISO date) |
| `--until "2026-04-14"` | End of analysis window (default: now) |
| `--dir /path/to/repos` | Root directory to scan for git repos (default: CWD) |
| `--repos "repo1,repo2"` | Only include these repos (comma-separated names) |
| `--skip-eff` | Skip effective-code analysis — 5-10x faster |
| `--output report.html` | Custom output path (default: `<system-tempdir>/code-report-YYYY-MM-DD.html`, e.g. `/tmp/code-report-2026-04-14.html` on macOS/Linux) |
| `--dump-commits <path>` | **Review pass 1** — dump per-author commit metadata (sha/message/numstat/files) to JSON and exit. The agent reads this dump to write reviews. No HTML produced. |
| `--reviews-json <path>` | **Review pass 2** — inject an LLM-generated `贡献点评` section into the HTML, placed before `每日代码提交趋势`. Omit this flag to skip the review section entirely. |

## Usage Examples

Replace `${SKILL_DIR}` with this skill's actual path when executing:

```bash
# Single repo, last week (fast mode)
python3 "${SKILL_DIR}/scripts/codereport.py" --since "7 days ago" --dir /path/to/repo --skip-eff

# Multi-repo, last week with effective code
python3 "${SKILL_DIR}/scripts/codereport.py" --since "7 days ago" --dir /path/to/repos

# Specific repos and date range
python3 "${SKILL_DIR}/scripts/codereport.py" --since "2026-04-07" --until "2026-04-14" \
  --dir /path/to/repos --repos "debox-iOS,debox-android,debox-web"

# Monthly report
python3 "${SKILL_DIR}/scripts/codereport.py" --since "30 days ago" --dir /path/to/repos --skip-eff
```

## Contribution Reviews (optional)

When the user asks for per-contributor reviews, scoring, or "点评 / 评分 / 绩效", switch to the **two-pass workflow**. The script never calls an LLM — it prepares data and renders results. The agent (you) produces the judgments in between.

### Pass 1 — Dump commits

```bash
python3 "${SKILL_DIR}/scripts/codereport.py" --since "7 days ago" \
  --dir /path/to/repos --skip-eff \
  --dump-commits /tmp/commits-dump.json
```

The dump is a JSON document of this shape:

```json
{
  "window": {"since": "2026-04-07", "until": "2026-04-14"},
  "rubric": {
    "formula": "总分 = 产出×20% + 质量×30% + 影响×30% + 协作与长期价值×20%",
    "scale": "每项 0-100",
    "dimensions": ["output", "quality", "impact", "collab"]
  },
  "authors": {
    "Alice": {
      "total_commits": 14,
      "total_insertions": 1820,
      "total_deletions": 430,
      "repos": ["service-api", "service-web"],
      "commits": [
        {
          "repo": "service-api", "repo_url": "https://github.com/org/service-api",
          "sha": "abc123…", "short": "abc123",
          "author": "Alice", "raw_author": "alice-dev", "email": "alice@example.com",
          "date": "2026-04-09T14:20:11+08:00",
          "subject": "feat(auth): rotate refresh tokens on session reuse",
          "insertions": 186, "deletions": 42,
          "files": [{"path": "auth/session.py", "ins": 120, "del": 20}, ...]
        }
      ]
    }
  }
}
```

### Pass 2 — Write reviews and render

Read the dump, think about each contributor, and write a `reviews.json` matching this schema:

```json
{
  "rubric": {"formula": "总分 = 产出×20% + 质量×30% + 影响×30% + 协作与长期价值×20%"},
  "reviews": [
    {
      "author": "Alice",
      "summary": "本期围绕认证会话安全进行了重构，核心是双写 + 滚动刷新令牌，影响全站登录链路。",
      "works": [
        {
          "title": "重构 refresh token 轮转策略",
          "complexity": "high",
          "business": "登录安全（合规强相关）",
          "risk": "影响所有在线会话；需配合灰度",
          "evidence": ["abc123", "def456"]
        },
        {
          "title": "补齐 session 模块单元测试",
          "complexity": "medium",
          "business": "质量保障",
          "risk": "低",
          "evidence": ["789abc"]
        }
      ],
      "quality": {
        "issues": "一处竞态在 code review 中被 Bob 发现并修复",
        "rework": "refresh_token.py 第二次迭代重写"
      },
      "long_term": "session 抽象层抽出后，后续 OAuth 接入成本显著降低；补齐测试提升了后续改动信心。",
      "scores": {"output": 82, "quality": 78, "impact": 90, "collab": 85},
      "total": 83.9
    }
  ]
}
```

Then re-run the script with the review JSON to produce the final HTML:

```bash
python3 "${SKILL_DIR}/scripts/codereport.py" --since "7 days ago" \
  --dir /path/to/repos --skip-eff \
  --reviews-json /tmp/reviews.json
```

### Rubric

Grade each contributor on four 0-100 dimensions. The weighted total is:

```
总分 = 产出 × 20% + 质量 × 30% + 影响 × 30% + 协作与长期价值 × 20%
```

Compute `total` yourself — the script renders whatever you put in the JSON. If `total` is missing the renderer will derive it from the four dimensions, but prefer being explicit.

- **产出 (output, 20%)** — volume and breadth of delivered work: commits, lines, features shipped. High volume alone is not high score; weight toward real deliverables.
- **质量 (quality, 30%)** — code correctness, test coverage, review feedback, bug-fix vs rework ratio. Deduct when reverts or post-merge fixes appear in the same window.
- **影响 (impact, 30%)** — business/system value: does this unlock revenue, unblock teammates, harden an incident-prone path? A small commit touching a critical path can outscore a large refactor nobody needed.
- **协作与长期价值 (collab, 20%)** — reviews given, tests and docs added, refactors that reduce future cost, knowledge sharing. Pure solo streaks cap here.

### Writing the review text

- **Summary**: 1–2 sentences. Frame the contributor's *theme* for the period, not a commit list.
- **Works**: 2–5 items. Each needs a title, a complexity tag (`high`/`medium`/`low`), a one-line business link, a risk note, and evidence SHAs (short hashes). Group related commits under one work item — don't list every commit.
- **Quality**: Only include if there are real findings. An empty or omitted `quality` block renders nothing, which is fine.
- **Long-term**: One paragraph on what this contributor left behind that will still matter in 3 months.
- **Evidence chain**: Always cite 1-3 short SHAs per work item so scores are auditable. The report renders them as inline code chips.

Be direct but fair. If someone had a light week, say so in the summary and let the scores reflect it — don't pad.

1. **Scans** directory recursively for git repos (skips node_modules, Pods, etc.)
2. **Collects** raw stats via `git log --shortstat` for each repo
3. **Analyzes** effective code via `git log -p` with comment/blank line filtering (optional)
4. **Merges** results across repos, normalizing author aliases
5. **Generates** HTML report at `<system-tempdir>/code-report-YYYY-MM-DD.html` (override with `--output`)

## Author Identity Config

The script no longer hardcodes any names. Instead it reads and writes a JSON config:

```
${SKILL_DIR}/scripts/authors.json   (default; override with --authors-config)
```

**File shape:**

```json
{
  "authors": [
    {
      "canonical": "Display Name",
      "aliases": ["git-name-1", "git-name-2"],
      "emails": ["user@example.com", "alt@example.com"]
    }
  ]
}
```

**Lifecycle on every run:**

1. At startup, the script loads `authors.json` and builds an alias → canonical map. Any git author name that matches an `aliases` entry (or a `canonical`) is collapsed under the canonical name in the report.
2. During analysis, the script harvests every `(name, email)` pair seen in the commit window.
3. After the HTML is written, any newly-encountered author name is appended as a fresh entry with `canonical = <raw git name>`, empty `aliases`, and its email(s). Newly-seen emails for known authors are appended to the existing entry.
4. Use `--no-update-authors` to disable the write-back.

**Merging duplicates — Agent-driven review (do this after every run that added entries):**

The script captures raw `(name, email)` pairs but never guesses which of them belong to the same human. That judgment call is yours. After the script reports `Updated authors.json: +N entries`, run this loop:

1. **Read** the current `authors.json`.
2. **Propose merges** by looking for evidence across entries:
   - **Shared email** — two entries with the same address in `emails` are almost certainly the same person.
   - **Name ↔ transliteration** — e.g. a Chinese name and a Pinyin/English handle sharing an email or a corporate domain.
   - **Handle variants** — casing differences (`alice` / `Alice`), numeric suffixes (`dev42` / `dev42x`), common prefixes with a `-work` / `-personal` tail.
   - **Corporate vs personal email** on otherwise identical display names.
   Do NOT merge on name similarity alone when emails disagree and there is no other signal — two people can share a first name.
3. **Present each proposed merge to the user with the evidence**, e.g.:
   > Merge `Alice Example` + `aexample` → canonical `Alice`?
   > Evidence: both commit from `alice@example.com`. Confirm? (y / n / pick different canonical)
4. **On confirmation**, edit `authors.json`: pick one entry as the survivor, set its `canonical` to the user's chosen display name, move the other raw names into its `aliases` list, union the `emails`, and delete the absorbed entries.
5. **Leave uncertain cases alone** and tell the user which entries you skipped and why — better a missed merge than a wrong one.

Subsequent runs will then normalize those names automatically, and the config keeps learning. No need to re-teach the script who is who each time.

## Report Sections

1. **Overview cards** - Total commits, raw lines, effective code, net change
2. **Raw lines table** - Per author commits/insertions/deletions (all files)
3. **Effective code table** - Per author after filtering comments/blanks (code files only)
4. **Daily commit trends** - Stacked bar chart
5. **Daily breakdown** - Per author per day net lines
6. **Filter comparison** - Raw vs effective, showing filter percentage
7. **Repository list** - Every analyzed repo with a clickable remote URL (normalized from SSH/HTTPS origin), its commit count in the window, and the last commit's short SHA (linked to the commit page) + timestamp

## Performance Tips

- `--skip-eff` is **5-10x faster** (skips diff parsing and line classification)
- Use `--repos` to limit scope instead of scanning all 70+ repos
- Large repos (10k+ commits in period) may take several minutes for effective analysis

## Dependencies

```bash
pip3 install pygments
```
