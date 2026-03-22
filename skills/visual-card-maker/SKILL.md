---
name: visual-card-maker
version: 1.0.0
author: 0xqige
description: "Use when converting any content (text, article, data, notes) into a visual image card. Triggers: turn content into image, make a card image, create visual card, generate cover image, content to image, make shareable card, article card, social media image, WeChat cover, info card, visual summary card."
allowed-tools: [Write, Read, Bash, WebFetch]
---

# Visual Card Maker

Convert any content (text, articles, data, notes) into a beautiful exportable image card — for article illustrations, cover images, or social sharing.

## Core Design Principles

Design decisions must follow these structural principles, not intuition or decorative instinct.

### Content Strategy

| Principle | Requirement | Design Action |
|-----------|-------------|---------------|
| **Information Compression** | Compress complex content into one clear claim | Single focus, remove redundancy, extract core message |
| **Attention First** | Capture attention in the first 3 seconds | Oversized title/number as visual anchor, de-emphasize secondary info |
| **Emotional Trigger** | Virality relies on emotion, not aesthetic complexity | Use contrast colors, motion, and tension to create emotional impact |

### Visual Structure

| Principle | Requirement | Design Action |
|-----------|-------------|---------------|
| **Clear Hierarchy** | Reading path requires no thinking | 3+ font size levels (64px → 24px → 14px), clear primary/secondary |
| **Contrast-Driven** | Create hierarchy through difference | Pull apart size, color, position, weight simultaneously |
| **Whitespace & Restraint** | Control element count, preserve breathing room | 16-28px spacing between elements, avoid filling every corner |

### Systematic

| Principle | Requirement | Design Action |
|-----------|-------------|---------------|
| **System Consistency** | Follow a unified visual system | Fixed color palette, font stack, spacing system — no one-off creativity |
| **Replicable** | Modular, templated, scalable | Consistent component structure, variable colors/text, batch-generatable |
| **Thumbnail Legible** | Core info readable at tiny size | Title/key data occupies 40%+ of area, avoid detail-dependency |

### UX

| Principle | Requirement | Design Action |
|-----------|-------------|---------------|
| **Cognitive Load Reduction** | Reduce mental cost of reading, judging, understanding | One block = one message, avoid competing tasks |

**Priority order:** Information Compression > Clear Hierarchy > Attention First > Others

---

## Workflow

### Step 1: Confirm Design Parameters

**1.1 Check user input**

```
IF user input is empty THEN
  Output: "Please provide content text, or tell me where to read it (URL, file path, or paste text)"
  Wait for user input
ELSE
  Proceed to 1.2 Content Analysis
END IF
```

**1.2 Content Analysis**

Analyze user content and identify these dimensions:

| Attribute | Evaluation Points | Example |
|-----------|-------------------|---------|
| **Content Type** | Data report / Opinion piece / Product intro / News / Personal brand | "Q3 revenue +30%" → Data report |
| **Emotional Tone** | Serious/professional / Lighthearted / Tech-future / Classic/retro / Rebel/avant-garde | "Disrupting the industry" → Rebel |
| **Information Density** | High (many data points) / Low (single focus) | 5 points + 3 data → High density |
| **Target Audience** | Business / Youth / Tech community / General public / Industry experts | "Series B funding" → Business/investors |
| **Distribution Channel** | Social media / Newsletter / Industry report / Brand / Portfolio | "Xiaohongshu share" → Social media |

**1.3 Recommend Design Style**

Based on content attributes, recommend the 4 best-matching styles from these 8 classic digital media styles:

| Style | Visual Traits | Best For | Color Tendency |
|-------|---------------|----------|----------------|
| **Bauhaus Modernism** | Geometric composition, functionalism, no decoration | Structured content, tech topics, education | Primary red/yellow/blue + B&W |
| **Swiss International** | Grid system, sans-serif, strong order | Data reports, academic content, professional news | B&W dominant + single accent |
| **Memphis** | High-contrast colors, decorative shapes, visual tension | Youth audience, creative content, events | Vibrant clashing colors |
| **Apple Minimal Tech** | Large whitespace, bold visuals, restrained typography | Product intro, brand identity, premium positioning | Black/white/gray + brand accent |
| **Wired Digital Futurism** | Experimental typography, tech composition, info-dense | Tech news, cutting-edge topics, data viz | Dark background + neon accents |
| **MTV Visual Collage** | Rebellious, image overlay, dynamic symbols | Pop culture, youth topics, entertainment | High saturation, strong contrast |
| **NYT Classic Press** | Rigorous layout, strong structure, authoritative | Long-form reporting, analysis, professional commentary | B&W + newsprint/red accents |
| **Monocle Contemporary** | Restrained palette, balanced text/image, ordered | Lifestyle, brand stories, profiles | Low saturation, warm tones |

**Matching rules:**

```
Content Attribute          →  Recommended Styles (priority order)
──────────────────────────────────────────────────────────────────
Serious/professional + data  →  Swiss / NYT / Bauhaus / Apple
Tech-future + cutting-edge   →  Wired / Apple / Swiss / Bauhaus
Youth + lively               →  Memphis / MTV / Apple / Monocle
Brand + premium              →  Apple / Monocle / Swiss / Bauhaus
Rebel + creative             →  MTV / Memphis / Wired / Bauhaus
Classic + in-depth           →  NYT / Monocle / Swiss / Apple
Lifestyle + restrained       →  Monocle / Apple / Swiss / Bauhaus
```

**1.4 Parameter Selection**

Ask user to confirm 4 dimensions:

| Dimension | Options | Default | Recommendation |
|-----------|---------|---------|----------------|
| **Aspect Ratio** | `9:16` / `3:4` / `1:1` / `4:3` / `16:9` / `2.35:1` | `9:16` | Based on target platform |
| **Design Style** | Choose from 4 recommended in 1.3 | First recommendation | Matched to content attributes |
| **Content Mode** | `Full` / `Condensed` | `Full` | Condensed for high-density content |
| **Add-ons** | `Screenshot tool` / `Noise texture` / `None` | `Screenshot tool` | Based on needs |

Aspect ratio guidance:
- 9:16, 3:4 → Info cards, can carry more content
- 16:9, 2.35:1 → Cover images, keep content concise, horizontal layout
- 1:1 → Social media sharing, moderate condensing

**1.5 Clarification**

Before proceeding to Step 2, confirm with user if any of the following are unclear:
- Content topic is ambiguous
- Core data / key information cannot be identified
- Brand / color requirements are vague
- Target platform is uncertain

---

### Step 2: Generate HTML

Generate a complete HTML file following the specs below. **File must be written to the system temp directory:**
- macOS/Linux: `/tmp/visual-card-<timestamp>.html`
- Windows: `%TEMP%\visual-card-<timestamp>.html`

#### 2.1 Dimensions & Container (CRITICAL)

```css
/* Container must use fixed pixel dimensions, all content must fit without scrolling */
.card-wrapper {
  width: {width}px;
  height: {height}px;
  overflow: hidden; /* required */
  position: relative;
}
```

All content must fit within the fixed container without scrolling. Estimate content volume before generating, then adjust font size and spacing by item count:
- ≤3 items: large fonts, loose spacing
- 4–6 items: medium fonts, moderate spacing
- ≥7 items: compact fonts, compressed spacing, consider multi-column layout

**Space utilization (CRITICAL): Content must fill the container. No large empty areas.**

Rules to prevent whitespace:
1. **Natural content height** — use `flex: 0 1 auto` not `flex: 1` on content areas
   ```css
   /* GOOD */
   .content-area { flex: 0 1 auto; }
   /* BAD */
   .content-area { flex: 1; }
   ```
2. **No forced card stretch** — don't use `flex: 1` inside cards; let content decide height
   ```css
   /* GOOD */
   .section-card { padding: 20px 28px; }
   /* BAD */
   .section-card { flex: 1; display: flex; flex-direction: column; }
   ```
3. **Precise grid allocation** — use `grid-template-rows` and `grid-template-columns` with `1fr` to fill remaining space
4. **Moderate padding** — 16–24px inside cards, 16–28px between sections
5. **Font scaling** — when space is tight, shrink fonts before truncating (body → subtitle → title)
6. **Decorative fill** — if content is sparse, fill gaps with geometric shapes, lines, or small icons
7. **Vertical distribution** — use `justify-content: space-between` for even vertical spacing

#### 2.2 Typography

**Core rule: Large bold primary text + small uppercase English accents = strong visual contrast.**

```css
.hero-title  { font-size: 64-80px; font-weight: 800; }
.hero-number { font-size: 48-72px; font-weight: 900; }
.en-subtitle { font-size: 14-18px; letter-spacing: 2-4px; text-transform: uppercase; opacity: 0.6; }
.body-text   { font-size: 18-24px; line-height: 1.5-1.6; }
```

Font stack:
```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Noto Sans SC", sans-serif;
```

#### 2.3 Icon Library (REQUIRED)

Load a professional icon library via CDN. Never use emoji as primary icons.

```html
<!-- Choose one -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<!-- or -->
<link rel="stylesheet" href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined">
```

Use icons for: category labels, data metrics, list prefixes, decorative elements.

#### 2.4 Color & Effects

**Accent color rule: use each accent color independently with opacity gradients. Never blend different accent colors in a single gradient.**

```css
/* GOOD: single-color opacity gradient */
background: linear-gradient(135deg, rgba(59,130,246,0.2), rgba(59,130,246,0.05));

/* BAD: multi-color mixed gradient */
background: linear-gradient(135deg, rgba(59,130,246,0.2), rgba(139,92,246,0.2));
```

**Dark Tech preset:**
```css
--bg: #0a0e1a;
--card-bg: rgba(15,23,42,0.8);
--accent-1: #3b82f6;  /* blue */
--accent-2: #06b6d4;  /* cyan */
--accent-3: #8b5cf6;  /* purple */
--accent-4: #10b981;  /* green */
--accent-5: #f59e0b;  /* amber */
```

**Light Minimal preset:**
```css
--bg: #fafafa;
--card-bg: #ffffff;
--accent-1: #1a1a2e;
--accent-2: #0066ff;
--text: #1a1a2e;
--text-secondary: #6b7280;
```

**Apple style preset:**
```css
--bg: #000000;
--card-bg: #1c1c1e;
--accent: #0071e3;
--text: #f5f5f7;
--text-secondary: #86868b;
```

**Notion style preset:**
```css
--bg: #ffffff;
--card-bg: #f7f6f3;
--accent: #2eaadc;
--text: #37352f;
--text-secondary: #787774;
--border: #e3e2de;
/* Minimal lines, soft radius (6-8px), no or very light shadows */
```

**Parchment preset:**
```css
--bg: #faf8f0;
--card-bg: #f5f0e3;
--accent: #c9a96e;
--text: #3d3929;
--text-secondary: #8a7e6b;
/* Warm tones, serif accents, thin borders, vintage feel */
```

#### 2.5 Visual Elements

**Required elements:**

1. **Line-art graphics** — SVG or CSS linear shapes for decoration or data visualization
```css
.line-deco {
  border: 1px solid rgba(accent, 0.1);
  border-radius: 50%;
}
```

2. **Size contrast** — oversized elements (title/number/bg decoration) vs. small elements (English labels/thin lines/small icons)

3. **Background layering** — at least 2–3 background decoration layers (grid lines / glow / geometric shapes) for depth

#### 2.6 Layout Patterns

**Bento Grid (recommended for data-dense content):**
```css
.bento-grid {
  display: grid;
  grid-template-columns: repeat(auto, ...);
  grid-template-rows: repeat(auto, ...);
  gap: 12-20px;
}
/* Key: different cards occupy different grid areas — large cards for core data, small for supporting info */
```

**Magazine (for narrative content):**
- Left/right columns or top/bottom sections
- Large whitespace
- Image/headline dominates
- Text wraps around visual focal point

**Card-Based (for equal-weight items):**
- Uniform card grid
- Consistent card structure
- Good for parallel points/data

**Tile (for dense information):**
- Tightly packed color blocks
- No or minimal gap
- Color differentiates information zones

#### 2.7 Condensed Mode

When user selects "Condensed":
- Extract 3–5 most essential points from source content
- Compress each point to one phrase (under 15 characters)
- Keep the 2–3 most impactful data points
- Rewrite title as a punchy short statement
- Best for 16:9 and 2.35:1 cover formats

---

### Step 3: Quality Check

Self-review after generation:

- [ ] All content fits within fixed dimensions (no scrolling)
- [ ] Professional icon library loaded via CDN, no emoji icons
- [ ] Clear contrast between large bold primary text and small uppercase English accents
- [ ] Each accent color used independently, no multi-color mixed gradients
- [ ] At least one line-art decorative element included
- [ ] Large vs. small element contrast creates visual impact
- [ ] Font sizes adjusted appropriately for content volume
- [ ] **High space utilization — no large empty areas**
- [ ] **grid-template-rows or flex layout used to fill container**
- [ ] Bento Grid cards tightly packed, filling available space

---

### Step 4: Preview & Export

**Write the HTML file to the system temp directory, then open in browser.**

File naming: `visual-card-<timestamp>.html`

```bash
# macOS / Linux
open /tmp/visual-card-$(date +%s).html

# or use $TMPDIR (preferred on macOS)
open "${TMPDIR:-/tmp}visual-card-$(date +%s).html"
```

**File path must use `/tmp/` prefix (macOS/Linux) or `%TEMP%` (Windows). Never write to the current working directory.**

#### Screenshot Export

Full implementation in `scripts/screenshot-utils.js`. Integration steps:

1. **Add to `<head>`:**
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
```

2. **Inline before `</body>`** — paste full contents of `scripts/screenshot-utils.js` (toolbar HTML + CSS + JS)

3. **Key config** (must match the actual card background color):
```js
const SCREENSHOT_CONFIG = {
  target: '.card-wrapper',
  scale: 2,
  filename: 'visual-card',
  bgColor: '#actual-bg-color'  // must match --bg CSS variable
};
```

> Clipboard requires HTTPS or localhost — `file://` protocol is restricted.

---

### Step 5: Next Step

**5.1 Ask user what to do next:**

```
Options:
  [A] Preview alternative designs — generate different style variations
  [B] Refine current design — adjust details (color / font / layout / content)
  [C] Done — satisfied with result, end workflow
```

**5.2 Option A: Alternative designs**

Offer 4 differentiated variations (multi-select allowed):

| Option | Layout | Color | Differentiator |
|--------|--------|-------|----------------|
| **A** | Different from current | Different style | Alternative design |
| **B** | Different from current | Different style | Alternative design |
| **C** | Different from current | Different style | Alternative design |
| **D** | Different from current | Different style | Alternative design |

Each selected option independently runs **Step 2 → Step 3 → Step 4**.

**5.3 Option B: Refine current design**

```
Ask user which dimension to refine:
  [Color]   — swap color scheme
  [Layout]  — restructure layout
  [Font]    — adjust size/weight
  [Content] — add, remove, or condense content
  [Deco]    — add or remove decorative elements
```

Based on selection, return to **Step 2** to regenerate.

**5.4 Option C: Done**

```
Output: "Design complete!"
File: /tmp/visual-card-<timestamp>.html
Note: "File saved to system temp directory. Open in browser to preview, use screenshot buttons to export."
End workflow.
```

---

**Workflow diagram:**

```
User provides content
        │
        ▼
┌─────────────────┐
│  Step 1: Setup  │◄─────────────────────┐
└────────┬────────┘                       │
         ▼                                │
┌─────────────────┐                       │
│ Step 2: Generate│                       │
└────────┬────────┘                       │
         ▼                                │
┌─────────────────┐                       │
│  Step 3: Check  │                       │
└────────┬────────┘                       │
         ▼                                │
┌─────────────────┐                       │
│ Step 4: Export  │                       │
└────────┬────────┘                       │
         ▼                                │
┌─────────────────────────────────────────┤
│           Step 5: Next Step             │
│                                         │
│  [A] Alternatives ──► Step 2 (new)      │
│  [B] Refine ────────────────────────────┘
│  [C] Done ──────────► End
└─────────────────────────────────────────┘
```

---

## Common Errors

| Problem | Cause | Fix |
|---------|-------|-----|
| Content overflow / clipped | Font too large or spacing too wide | Estimate content volume first, then set font/spacing |
| Looks like a regular webpage | Missing decoration and visual hierarchy | Add background grid, glow, line-art shapes |
| No visual focal point | All elements are similar in size | Enlarge core data/title, shrink supporting info |
| Colors look muddy | Multi-color gradient mixing | Use single-color opacity variation per accent |
| Cheap/amateurish look | Used emoji icons | Replace with Font Awesome / Material Icons |
| English accents feel forced | English text too large or too frequent | Keep English small, uppercase, wide letter-spacing, low opacity |
| **Large empty areas** | Padding too large, grid row heights uncontrolled, content not flex-filling | Use `grid-template-rows` proportionally, `flex: 1` to expand, reduce padding to 16-24px |
| **Empty areas (container level)** | `.content-area` using `flex: 1` forces full height with sparse content | Use `flex: 0 1 auto` for natural height |
| **Empty areas (card level)** | `.section-card` with `flex: 1` + `display: flex` force-stretches card | Remove flex layout from cards, let content decide height |
| **Bottom gap** | Fixed container height with insufficient content | Use `justify-content: space-between`, or add decorative elements at bottom |

---

## Quick Reference

**Size chart:**

| Ratio | Pixels | Use Case |
|-------|--------|----------|
| 9:16 | 1080×1920 | Mobile info cards |
| 3:4 | 1080×1440 | Info cards / Xiaohongshu |
| 1:1 | 1080×1080 | Social media sharing |
| 4:3 | 1440×1080 | Landscape info display |
| 16:9 | 1920×1080 | Cover / landscape display |
| 2.35:1 | 1920×817 | WeChat article cover |
