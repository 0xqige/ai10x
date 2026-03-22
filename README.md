# ai10x

> 让 AI 成为真正的结对编程助理，帮助开发者实现 10 倍效率提升。

围绕 AI 辅助编程所沉淀的高效工具与脚本集合。

## 包含内容

### Skills（Claude Code 技能）

可被 Claude Code 自动触发的自定义工作流，将复杂任务封装为可复用流程。

| 技能 | 描述 |
|------|------|
| [visual-card-maker](./skills/visual-card-maker/SKILL.md) | 将任意内容转换为精美的可导出图片卡片（文章封面、信息卡、社交媒体图） |

**使用方式**：将 `skills/` 目录下的技能复制到 Claude Code，即可在对话中自动触发对应工作流，推荐使用工具配置。

```sh
npx skills add 0xqige/ai10x
```
