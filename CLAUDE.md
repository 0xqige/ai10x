# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库概述

**ai10x** 是围绕 AI 辅助编程所沉淀的高效工具与脚本集合，目标是让 AI 成为真正意义上的结对编程助理，帮助开发者实现 10 倍效率提升。

核心内容包括：
- **Claude Code Skills**：可被 Claude Code 触发的自定义技能，封装复杂工作流为可复用流程
- **辅助脚本**：配合技能运行的工具函数（截图、转换、自动化等）
- （持续沉淀中）

## 目录结构

```
skills/
  <skill-name>/
    SKILL.md              # 技能定义文件（frontmatter + 使用说明）
    scripts/              # 技能所需的辅助脚本（可选）
```

## SKILL.md 文件格式

每个技能文件必须包含 YAML frontmatter：

```yaml
---
name: skill-name
version: 1.0.0
author: username
description: "触发描述 — 何时调用此技能"
allowed-tools: [Write, Read, Bash, WebFetch]
---
```

- `description` 字段决定技能何时被触发，需清晰描述触发场景
- `allowed-tools` 限制技能可使用的工具列表

## 现有技能

### visual-card-maker

将任意内容（文字、文章、数据、笔记）转换为可导出的视觉图片卡片。

**触发词**：将内容转为图片、制作卡片图、生成封面图、内容转图、制作分享卡片、文章卡片、社交媒体图片、微信封面、信息卡、可视化摘要卡。

**核心流程**：
1. 分析内容属性（类型、情绪基调、信息密度、受众、渠道）
2. 推荐 4 种匹配设计风格（Bauhaus / Swiss / Memphis / Apple Minimal 等 8 种之一）
3. 确认参数（宽高比、风格、内容模式、附加功能）
4. 生成 HTML 文件，写入 `/tmp/visual-card-<timestamp>.html`
5. 用浏览器打开预览

**截图导出**：依赖 `scripts/screenshot-utils.js`（基于 html2canvas），通过 CDN 加载后内联到生成的 HTML 中。`SCREENSHOT_CONFIG.bgColor` 必须与卡片实际背景色一致。

**关键约束**：
- HTML 容器使用固定像素尺寸 + `overflow: hidden`，所有内容不得溢出
- 禁止使用 emoji 作为主要图标，必须通过 CDN 加载 Font Awesome 或 Material Icons
- 每种强调色独立使用渐变，禁止多色混合渐变
- 文件必须写入系统临时目录，不写入当前工作目录
