# llm-wiki

一个为 AI 代码助手设计的 **Karpathy-style LLM Wiki** 模式，用于将原始资料转化为结构化、相互关联的 Markdown 知识库，并将查询结果归档回 wiki 中。

> **核心原则：** Wiki 是一个**持久且复利增长**的产物。每一次内容摄取和每一次查询归档都会让它更丰富。交叉引用预先建立，矛盾之处预先标记。知识只需编译一次并保持更新，而不是每次查询都重新推导。

本仓库是 [Andrej Karpathy 的 LLM Wiki 模式](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 的一个具体实现。Karpathy 在其 Gist 中提出了一个关键洞察：大多数人与 LLM 和文档的交互方式像 RAG——每次查询时从原始文档中检索，没有积累；而 LLM Wiki 的做法是让 LLM **增量式地构建并维护一个持久的 wiki**，在原始来源和查询之间插入一个结构化、相互关联的 Markdown 层。当你添加新来源时，LLM 不只是索引它，而是阅读它、提取关键概念、更新相关页面、建立交叉引用。这样，wiki 本身就成为了一个**持久且复利增长**的产物。

---

## 快速开始

| 命令 | 操作 |
|---------|---------|
| `/wiki ingest <path>` | 读取文件或网页，保存到 `raw/`，然后编译进 wiki |
| `/wiki query "<question>"` | 搜索 wiki 并综合答案（自动保存到 wiki） |
| `/wiki lint` | 对 wiki 进行健康检查：矛盾、孤立页面、知识缺口 |
| `/wiki sync` | 扫描 `.learning` 目录 → 将新增/变更的文件自动摄取到 wiki |

---

## 项目结构

```
llm-wiki/
├── SKILL.md              # 技能主文档（触发词 /wiki）
├── RULES.md              # 执行规则（任何 /wiki 命令前必须阅读）
├── scripts/
│   └── learning_scanner.py  # 扫描 .learning 目录并生成摄取报告
├── raw/                  # 原始资料（不可变）
│   └── articles/
├── wiki/                 # 结构化 wiki 内容
│   ├── index.md          # 索引：概念、实体、来源摘要、查询答案
│   ├── overview.md       # 领域综合概述
│   ├── log.md            # 操作日志（摄取、查询、lint）
│   ├── concepts/         # 概念页面（术语、技术、框架）
│   ├── entities/         # 实体页面（人物、组织、工具）
│   ├── sources/          # 来源摘要页面
│   ├── queries/          # 已归档的查询答案
│   └── comparisons/      # 比较表格/图表
└── .wiki/                # 工具状态与索引
    ├── learning_index.json
    └── ingest_manifest.json
```

---

## 核心工作流

### 1. 内容摄取 (Ingest)

将新来源（文件、URL 或网页搜索结果）转化为结构化的 wiki 页面。

**关键步骤：**
1. 获取原始内容 → 保存到 `raw/articles/YYYY-MM-DD-topic.md`
2. 阅读 `wiki/index.md` 了解当前结构
3. 检查与现有内容的矛盾（如有）
4. 创建/更新 `wiki/sources/` 中的来源摘要页面
5. 提取 **3-6 个概念页面**到 `wiki/concepts/`
6. 提取实体页面到 `wiki/entities/`
7. 在页面间添加 `[[wiki-link]]` 交叉引用
8. 更新 `wiki/index.md` 和 `wiki/log.md`

### 2. 查询与归档 (Query & File)

针对 wiki 提问，系统自动综合答案并归档。

**特点：**
- 每个查询答案自动保存到 `wiki/queries/YYYY-MM-DD-slug.md`
- 答案中带有 `[[wiki-link]]` 引用
- 更新索引和日志

### 3. 健康检查 (Lint)

运行 `/wiki lint` 检查：
- **矛盾**：日期、数字、定义冲突
- **孤立页面**：未被 `[[...]]` 引用的页面
- **缺失页面**：频繁提及但无独立概念页的术语
- **过时主张**：被新来源取代的旧说法

---

## 配套工具

### Obsidian（推荐）
- **用途**：浏览 wiki、查看图谱视图、反向链接
- **建议**：从第一天开始使用

### qmd
- **用途**：混合 BM25/向量搜索 Markdown
- **建议**：当 `index.md` 超过舒适上下文窗口时（约 100+ 来源）

### Dataview
- **用途**：在 Obsidian 中查询 frontmatter
- **建议**：需要仪表盘（标签、来源数、过时页面）时

### Mermaid
- **用途**：在 Markdown 中绘制流程图和关系图
- **建议**：可视化流程、架构或关系时

---

## 规则摘要

- **永远不要写入 `raw/`。** 它是不可变的。
- 所有 wiki 页面必须使用 **frontmatter**。
- 始终使用 `[[wiki-link]]` 语法进行**交叉引用**。
- 每次操作后都要**记录日志**。
- 更新现有页面时优先使用 `edit` 而非 `write`。
- 与 schema 共同演进：发现新约定时，更新 `OPENCODE.md`。

---

## 跨产品适配

本技能设计为与具体 AI 产品解耦，可轻松移植到：
- Claude Code
- Codex (OpenAI)
- Trae
- Kimi Code
- CodeBuddy
- 其他支持 `.learning/` 目录的 AI 编程工具

移植时只需复制 `SKILL.md`、`RULES.md` 和 `scripts/learning_scanner.py`，并注册对应命令即可。

---

## License

MIT
