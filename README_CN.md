<div align="center">

# CodeAtlas

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-Local-003B57?style=for-the-badge)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br>

### 一次索引，永久查询。不上云，不花 token 费。

<br>

*一个本地优先的代码知识库工具，把 TypeScript / JavaScript / Python 项目转化为可索引、可查询的 SQLite 数据库 —— 让你无需逐文件阅读就能理解架构、追踪调用链、发现循环依赖、生成图表。*

**0.3 新增：** 内置 Web 可视化界面（`codeatlas serve`）、Python 支持、增量索引、循环依赖检测。

推荐与 **Claude Code**、**Codex** 或任何需要在提问前获取结构化上下文的 AI 代理配合使用。

[English README](README.md)

</div>

---

## CodeAtlas 是什么？

CodeAtlas 是一个**本地优先的代码知识库**。

你指向一个 TypeScript / JavaScript / Python 项目，它将代码索引到本地 SQLite 数据库中。之后你可以查询符号、追踪调用链、映射依赖关系、检测循环依赖、生成图表 —— 全部离线运行，全部免费，命令行和浏览器里都能用。

它不是代码搜索工具。它不是 AI 文档生成器。它是一个**结构化的代码索引**，注重的是深度而非广度。

---

## 什么时候该用 CodeAtlas？

- **理解陌生的代码仓库** — 直接跳到架构层面，跳过逐文件阅读
- **准备技术面试** — 生成调用图和依赖图来解释一个系统
- **编写架构文档** — 获取准确的符号清单和模块划分
- **探索大型 TypeScript / Python 项目** — 几秒内找到调用者、被调用者和依赖链
- **为 LLM 提供高质量上下文** — 将结构化分析结果喂给 Claude / GPT，获得更丰富的提示

如果你的任务涉及理解*代码之间的关系*，CodeAtlas 就是为此而生的。

---

## 为什么需要 CodeAtlas？

大型代码库很难理解。

只搜索符号是不够的。

阅读数百个文件太慢。

LLM 会反复扫描同一段代码，白白消耗 token。

**CodeAtlas 将你的项目索引到一个本地 SQLite 数据库中，解决这些问题。**

索引之后，你可以：

- **查找任意符号** — 函数、类、接口、类型、枚举、变量
- **追踪调用链** — 谁调用了它？它调用了谁？能追溯多深？
- **映射依赖关系** — 文件级别的下游（导入）和上游（被导入）关系
- **检测循环依赖** — 文件依赖图中的强连通分量
- **生成 Mermaid 图表** — 可视化的依赖图和调用图
- **产出架构报告** — 模块划分、符号统计、导入热力图
- **在浏览器里探索** — `codeatlas serve` 打开交互式依赖地图、文件浏览器和符号查看器

把它当作一个 **个人版 Sourcegraph Lite** — 不上云，不需要 API 密钥，没有按次计费。只是你的代码，本地索引，随时查询。

---

## 适合谁？

| 用户 | 场景 |
|------|------|
| **独立开发者** | 回到一个旧项目，不用重新读一遍代码就能理解架构 |
| **开源贡献者** | 在向不熟悉的项目提交 PR 之前，快速了解项目结构 |
| **AI 工程师** | 在提示 LLM 之前，先检索相关上下文（调用图、依赖报告） |
| **面试准备者** | 为高级工程师面试准备架构讲解 |
| **技术写作者** | 为文档生成准确的模块图和符号清单 |

---

## 它能生成什么？

### 架构报告

```
$ codeatlas stats

📊 SkyTerrain
   文件数:   59
   符号数: 1049
   导入数: 342
   调用数: 1598
   依赖数: 287

   符号分类:
     function              412
     class                  98
     interface              76
     type                   54
     enum                   23
     variable              386
```

### 依赖图（Mermaid）

```
$ codeatlas graph ExplorerApp --type deps

graph TD
    ExplorerApp --> CesiumMap
    ExplorerApp --> Camera
    ExplorerApp --> Terrain
    CesiumMap --> MapConfig
    CesiumMap --> TileProvider
    Camera --> Projection
    Terrain --> Heightmap
    Terrain --> Dataset
```

### 调用链

```
$ codeatlas chain handleSelectFeature --depth 2

🔗 调用链: handleSelectFeature()

    handleSelectFeature()
      → updateSelection()
      → renderFeature()
      → notifyListeners()
      updateSelection()
        → clearPrevious()
        → markActive()
      renderFeature()
        → drawGeometry()
        → applyStyle()
```

---

## 架构

```
你的项目（TS / JS / Python）
        │
        ▼
   ┌─────────┐
   │  扫描   │  遍历目录树，跳过 node_modules / dist / .venv / 隐藏目录
   └────┬────┘
        ▼
   ┌─────────┐
   │  解析   │  tree-sitter AST → 符号、导入、调用边
   └────┬────┘  （parser.py 按扩展名分发到 ts_parser / py_parser）
        ▼
   ┌─────────────┐
   │  解析路径   │  tsconfig 别名 + 扩展名顺序，或 Python 模块路径 ——
   └─────┬───────┘  始终相对于*发起导入的那个文件*
        ▼
   ┌──────────────┐
   │ SQLite 数据库 │  本地优先，WAL 模式，带版本的 schema，项目隔离
   │  ~/.codeatlas│  （内容哈希支撑增量索引）
   └─────┬────────┘
        │
        ▼
 ┌────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐
 │  查询  │ │ 图算法 │ │ 循环检测 │ │ Mermaid │ │  Web UI  │
 │  符号  │ │  BFS   │ │  Tarjan  │ │  导出   │ │ FastAPI  │
 └────────┘ └────────┘ └──────────┘ └─────────┘ └──────────┘
```

---

## 典型工作流

以下是一个开发者加入新项目时使用 CodeAtlas 的流程：

```
1. 克隆项目
        │
        ▼
2. 索引项目（一条命令）
   codeatlas index .
        │
        ▼
3. 探索架构
   codeatlas stats
   codeatlas symbols Camera
        │
        ▼
4. 追踪调用链
   codeatlas callers computeCameraFromRidge
   codeatlas chain handleSelectFeature --depth 3
        │
        ▼
5. 生成图表
   codeatlas graph Camera --type deps
        │
        ▼
6. 阅读自动生成的架构讲解
   codeatlas explain
   codeatlas serve          # ...或者直接在浏览器里探索
        │
        ▼
7. 将输出喂给 LLM 进行更深入的分析
   （或者直接阅读 — 不需要 LLM）
```

---

## 快速开始

### 1. 安装

```bash
pip install -e .            # 仅命令行
pip install -e ".[web]"     # 命令行 + Web 界面
```

### 2. 索引项目

```bash
# 索引当前目录
codeatlas index .

# 或者指定路径并自定义项目名称
codeatlas index ~/projects/my-app --name my-app
```

### 3. 查询索引

```bash
# 查看索引内容
codeatlas stats

# 按名称查找符号
codeatlas symbols Camera

# 查看谁调用了某个函数
codeatlas callers computeCameraFromRidge

# 查看某个函数调用了什么
codeatlas callees handleSelectFeature

# 追踪调用链
codeatlas chain handleSelectFeature --depth 3

# 生成 Mermaid 依赖图
codeatlas graph Camera --type deps

# 查看文件级依赖
codeatlas deps lib/terrain.ts
```

### 4. 或者在浏览器里探索

```bash
codeatlas serve
```

打开 `http://127.0.0.1:8000`：填一个目录路径（或直接拖进一个 `.zip`），看着它完成索引，
然后阅读自动生成的架构讲解、拖动缩放交互式依赖地图、浏览文件与符号、查看循环依赖。
服务只监听本机，读取的就是命令行写入的那份 SQLite 索引 —— 没有任何内容被上传。

就这么简单。你的知识库随时待查。

---

## 命令参考

所有命令都共享 `--project <name>` 标志来指定目标项目。

| 命令 | 说明 |
|------|------|
| `index <path> [--name NAME] [--verbose] [--incremental]` | 将 TS/JS/Python 项目索引到 SQLite |
| `serve [--host H] [--port P] [--no-open]` | 启动 Web 可视化界面 |
| `explain [--json]` | 输出结构化架构报告（模块、入口、核心文件、循环依赖） |
| `stats` | 显示索引统计（文件、行数、符号、导入、调用、依赖） |
| `projects` | 列出所有已索引的项目 |
| `symbols <name>` | 按名称查找符号（`*` 为通配符） |
| `file <path>` | 列出文件中定义的所有符号 |
| `imports <name>` | 查找哪些文件导入了给定符号 |
| `used-by <module>` | 查找哪些文件从某模块导入 |
| `list [--kind KIND] [--exported] [--limit N]` | 列出符号，可按类型或导出状态过滤 |
| `callers <name>` | 查找谁调用了给定符号 |
| `callees <name>` | 查找给定符号调用了什么 |
| `chain <name> [--depth N]` | 显示符号的递归调用链 |
| `cycles [--mermaid]` | 检测文件之间的循环导入 |
| `graph <target> [--type deps\|calls] [--direction downstream\|upstream] [--depth N]` | 生成 Mermaid TD 图表 |
| `deps <path> [--direction downstream\|upstream] [--depth N]` | 显示文件级依赖树 |
| `export [-o FILE]` | 将整份索引（报告 + 文件 + 符号）导出为 JSON |

再次运行 `index` 会完全重建索引。加上 `--incremental` 只会重新解析内容发生变化的文件 ——
在大仓库上快得多，结果完全一致。

---

## 与其他工具的关系

CodeAtlas 专注于**本地优先的结构化索引**。它面向那些想要精确、可查询的代码关系，而不依赖云端或 LLM 成本的开发者。

这个领域的其他工具采取了不同的路线：

- **ZRead** 使用并行 Agent 从代码生成 AI 驱动的 Wiki 页面。它生成人类可读的文档，支持 14+ 种语言，但需要 LLM 提供商。
- **DeepWiki** 提供 AI 生成的仓库文档，带有公共托管和团队协作功能。
- **Sourcegraph** 为大型代码库提供强大的代码搜索能力，包括远程仓库。

这些工具解决的是相关但不同的问题。CodeAtlas 用精确的、可查询的代码结构（调用图、依赖树、符号清单）替代了 AI 生成的叙述性文档 —— 全部离线运行。

---

## 常见问题

### 我的代码会发送到云端吗？

不会。所有内容都存储在本地 `~/.codeatlas/projects/<name>/index.db`。不需要网络连接。

### 需要 OpenAI 或任何 LLM 吗？

不需要。CodeAtlas 完全离线运行，是一个独立的 CLI 工具。

### 我能在提示 GPT/Claude 之前用它吗？

可以。很多用户先运行 CodeAtlas，然后把输出（调用链、依赖图、架构报告）粘贴到 LLM 会话中，获得更丰富的上下文。

### 支持哪些语言？

**TypeScript、TSX、JavaScript、JSX 和 Python**（`.ts .tsx .mts .cts .js .jsx .mjs .cjs .py .pyi`）。
新增一门语言只需要写一个 parser 模块，见 [CONTRIBUTING.md](CONTRIBUTING.md)。

### 数据存在哪里？

每个索引项目拥有自己的 SQLite 数据库，位于 `~/.codeatlas/projects/<project-name>/index.db`。数据库使用 WAL 模式保证并发读取安全。

### 可以重复索引同一个项目吗？

可以 —— 再次运行 `codeatlas index` 会覆盖之前的索引。加 `--incremental` 则只重新解析
内容变化过的文件。

### Web 界面会把我的代码传到哪里去吗？

不会。`codeatlas serve` 启动的是绑定在 `127.0.0.1` 的本地 FastAPI 服务，读取本地 SQLite
索引，前端是单个 HTML 文件、不请求任何 CDN。它能索引和读取当前用户能读的任意目录 ——
正因如此，请不要把它暴露到公网。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 编程语言 | Python 3.11+ |
| CLI 框架 | Click |
| AST 解析器 | tree-sitter（`tree-sitter-language-pack`，TSX + Python 语法） |
| 存储 | SQLite3（WAL 模式，带版本的 schema） |
| 图算法 | 可配置深度的 BFS；循环检测用 Tarjan 强连通分量 |
| 图表输出 | Mermaid TD 语法 |
| Web 界面 | FastAPI + 单个零依赖 HTML 文件（canvas 力导向布局） |

---

## 路线图

- [x] Python 解析器支持
- [x] 增量索引（仅变更文件）
- [x] 查询索引的 Web UI
- [x] 导入循环检测
- [x] 供程序调用的 JSON 导出
- [ ] 跨文件调用解析（目前 `call_edges` 存的是被调用者名字，查询时才解析）
- [ ] Go / Rust / Java 解析器
- [ ] 符号重命名 / 重构安全检查
- [ ] 监听模式（文件变更自动重新索引）

---

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
