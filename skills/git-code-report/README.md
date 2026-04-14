# git-code-report

Generate a polished HTML report analyzing git contributor activity across one or many repositories. The report covers commit volume, raw and effective line counts, daily trends, per-author sparklines, repository metadata, and an optional LLM-authored contribution review.

Built as a [Claude Code](https://claude.com/claude-code) skill — see `SKILL.md` for the agent-facing contract — but the bundled `scripts/codereport.py` is a standalone CLI you can run directly.

---

## Features

- **Single- or multi-repo** scanning. Recursively finds git repos under a root, skipping `node_modules`, `Pods`, etc.
- **Raw stats** (all files) and **effective stats** (code files only, comments and blank lines filtered out).
- **Daily commit trend** rendered as a pure-SVG line chart (no JS libraries).
- **Per-author trend overlay** with dual-layer hover hit targets so thin lines stay reachable.
- **Per-author daily breakdown table** with hover tooltips showing `insertions / deletions / net`.
- **Repository list** with clickable GitHub URLs, last-commit SHA, and timestamp.
- **Optional contribution review section** — a two-pass workflow where an LLM drafts scored reviews that the script renders into the final HTML.
- **Authors identity config** — a JSON registry that collapses multiple git identities (name/email variants) under one display name; auto-updates with newly-seen authors each run.

---

## Prerequisites

- Python 3.8+
- `git` on `PATH`
- `pygments` for effective-code line classification:

  ```bash
  pip3 install pygments
  ```

---

## Quick start

```bash
# Single repo, last 7 days
python3 scripts/codereport.py --since "7 days ago" --dir /path/to/repo

# Multi-repo root, specific window
python3 scripts/codereport.py \
  --since "2026-04-07" --until "2026-04-14" \
  --dir /path/to/repos-root

# Filter to a subset of repos
python3 scripts/codereport.py --since "30 days ago" \
  --dir /path/to/repos-root \
  --repos "service-api,service-web,service-mobile"

# Large org / huge repos — skip diff parsing for a 5-10x speedup
python3 scripts/codereport.py --since "30 days ago" --dir /path/to/repos-root --skip-eff
```

The report is written to the system temp directory as `code-report-YYYY-MM-DD.html` by default. Override with `--output /custom/path.html`. On macOS: `open /tmp/code-report-2026-04-14.html`.

---

## Contribution review workflow (optional)

The script does not call an LLM. Instead, it exposes two flags that let an LLM author the reviews in between two runs:

### Pass 1 — Dump commit metadata

```bash
python3 scripts/codereport.py --since "7 days ago" \
  --dir /path/to/repos \
  --dump-commits /tmp/commits-dump.json
```

This writes a JSON document grouping commits by author — sha, subject, date, numstat, files touched, repo, and remote URL — then exits without generating HTML.

### Pass 2 — Supply reviews and render

Feed the dump to an LLM (or write reviews yourself) following the schema in `SKILL.md`. Then rerun with `--reviews-json`:

```bash
python3 scripts/codereport.py --since "7 days ago" \
  --dir /path/to/repos \
  --reviews-json /tmp/reviews.json
```

The report gains a **Contribution Reviews** panel placed before the daily trend chart, with a tab-row selector to switch between contributors. Each review card shows the weighted total, four dimension bars, a work list with complexity tags, a quality / rework block, long-term value, and an evidence chain of short SHAs.

### Scoring rubric

```
total = output × 20% + quality × 30% + impact × 30% + collab × 20%
```

Each dimension is scored 0–100. See the `Rubric` section in `SKILL.md` for guidance on each dimension and how to write the review text.

---

## Authors identity config

`scripts/authors.json` is the source of truth for collapsing multiple git identities under one display name. Schema:

```json
{
  "authors": [
    {
      "canonical": "Alice",
      "aliases": ["alice-dev", "a.example"],
      "emails": ["alice@example.com", "alice@noreply.github.com"]
    }
  ]
}
```

Lifecycle per run:

1. On startup the config is loaded and an alias → canonical map is built.
2. During analysis every `(name, email)` pair encountered is harvested.
3. After HTML generation, newly-seen identities are appended as fresh entries (or newly-seen emails are added to existing ones).

Merge duplicates manually by picking a survivor entry, setting its `canonical`, moving the other names into its `aliases`, and unioning the `emails`. The skill documents an agent-driven merge review flow for this. Use `--no-update-authors` to disable the write-back.

---

## Flags

| Flag | Description |
|------|-------------|
| `--since <when>` | Start of analysis window. Git-log syntax (`"7 days ago"`) or ISO date. **Required.** |
| `--until <when>` | End of window. Default: now. |
| `--dir <path>` | Root directory to scan. Default: current directory. |
| `--repos "a,b,c"` | Comma-separated repo names to include. Default: all found under `--dir`. |
| `--skip-eff` | Skip effective-code analysis. 5-10x faster. Header cards and filter-comparison sections render placeholders explaining the skip. |
| `--output <path>` | Output HTML path. Default: `<system-tempdir>/code-report-YYYY-MM-DD.html`. |
| `--authors-config <path>` | Path to the authors JSON config. Default: `scripts/authors.json`. |
| `--no-update-authors` | Do not append newly-seen authors/emails back to the config. |
| `--dump-commits <path>` | **Review pass 1.** Dump per-author commit metadata and exit. No HTML produced. |
| `--reviews-json <path>` | **Review pass 2.** Inject an LLM-written contribution review section into the HTML. |

---

## Report sections

1. **Overview cards** — total commits, raw lines, effective lines, net change.
2. **Contribution reviews** *(only when `--reviews-json` is provided)*.
3. **Daily commit trend** — aggregate line chart across all repos.
4. **Per-author trend** — overlaid multi-line chart with hover highlight.
5. **Raw lines table** — per author, across all files.
6. **Effective code table** — per author, code files only, comments and blanks filtered.
7. **Daily breakdown table** — per author per day, net lines added, with `ins / del / net` tooltips.
8. **Filter comparison** — raw vs effective, showing how much was filtered out.
9. **Repository list** — every analyzed repo with remote URL, commit count, last commit SHA, and timestamp.

---

## Performance

- `--skip-eff` avoids the `git log -p` pass and per-line Pygments classification. On a 10k-commit / 10-repo window this drops runtime from a few minutes to seconds.
- Narrow the scope with `--repos` when you don't need everything under `--dir`.
- For the full-effective mode, the slow part is diff parsing; progress is logged per repo to stderr.

---

## License

This skill is part of the `ai10x` toolbox. See the repository root for licensing terms.
