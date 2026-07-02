<div align="center">

# CodeAtlas

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-Local-003B57?style=for-the-badge)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br>

### 一次索引，永久查询。不上云，不花 token 费。

<br>

*一个本地优先的代码知识库工具，将你的 TypeScript 项目转化为可索引、可查询的 SQLite 数据库 —— 让你无需逐文件阅读就能理解架构、追踪调用链、生成图表。*

推荐与 **Claude Code**、**Codex** 或任何需要在提问前获取结构化上下文的 AI 代理配合使用。

</div>

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
- **生成 Mermaid 图表** — 可视化的依赖图和调用图
- **产出架构报告** — 模块划分、符号统计、导入热力图

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

## 它能做什么？

| 能力 | 说明 |
|------|------|
| **符号搜索** | 按名称在整个项目中查找函数、类、接口、类型、枚举和变量 |
| **调用图** | 以可配置的深度（BFS）遍历谁调用了谁 |
| **依赖图** | 映射文件级别的下游（导入）和上游（被导入）关系 |
| **架构报告** | 获取文件数量、符号分类、导入热力图和模块摘要 |
| **模块分析** | 检查一个模块的符号、调用者、被调用者和依赖关系 |
| **Mermaid 导出** | 生成依赖图和调用链的 TD 图表 |
| **tsconfig 别名支持** | 解析 `tsconfig.json` 中的 `@/`、`~/` 等路径别名 |

---

## 架构

```
你的 TypeScript 项目
        │
        ▼
   ┌─────────┐
   │  扫描   │  遍历目录树，跳过 node_modules / dist / .git
   └────┬────┘
        ▼
   ┌─────────┐
   │  解析   │  tree-sitter AST → 符号、导入、调用边
   └────┬────┘
        ▼
   ┌─────────────┐
   │  解析路径   │  tsconfig 别名 + 扩展名解析
   └─────┬───────┘
        ▼
   ┌─────────────┐
   │  SQLite 数据库  │  本地优先，WAL 模式，项目隔离
   │  ~/.codeatlas│
   └─────┬───────┘
        │
        ▼
   ┌──────────┐    ┌──────────┐    ┌────────────┐
   │  查询    │    │  图算法  │    │  Mermaid   │
   │  符号    │    │  BFS     │    │  导出      │
   └──────────┘    └──────────┘    └────────────┘
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
6. 将输出喂给 LLM 进行更深入的分析
   （或者直接阅读 — 不需要 LLM）
```

---

## 快速开始

### 1. 安装

```bash
pip install -e .
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

就这么简单。你的知识库随时待查。

---

## 实际案例：SkyTerrain

索引一个 TypeScript 项目后，你会得到：

### 架构概览

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

## 命令参考

所有命令都共享 `--project <name>` 标志来指定目标项目。

| 命令 | 说明 |
|------|------|
| `index <path> [--name NAME] [--verbose]` | 将 TypeScript/TSX 项目索引到 SQLite |
| `stats` | 显示索引统计（文件、符号、导入、调用、依赖） |
| `symbols <name>` | 按名称在整个项目中查找符号 |
| `file <path>` | 列出文件中定义的所有符号 |
| `imports <name>` | 查找哪些文件导入了给定符号 |
| `used-by <module>` | 查找哪些文件从某模块导入 |
| `list [--kind KIND] [--exported]` | 列出符号，可按类型或导出状态过滤 |
| `callers <name>` | 查找谁调用了给定符号 |
| `callees <name>` | 查找给定符号调用了什么 |
| `chain <name> [--depth N]` | 显示符号的递归调用链 |
| `graph <target> [--type deps\|calls] [--direction downstream\|upstream] [--depth N]` | 生成 Mermaid TD 图表 |
| `deps <path> [--direction downstream\|upstream] [--depth N]` | 显示文件级依赖树 |

---

## 同类工具对比

### 与代码知识库工具的比较

| 特性 | CodeAtlas | [ZRead](https://github.com/bb-boy680/open-zread) | [DeepWiki](https://deepwiki.com) |
|------|-----------|--------------------------------------------------|----------------------------------|
| **核心方法** | 静态 AST 解析 + SQLite 存储 | AI Agent 并行生成 Wiki 页面 | AI 驱动 + 公共托管 |
| **存储** | 本地 SQLite | 本地 Markdown 文件 | PostgreSQL / SQLite + Web |
| **查询方式** | CLI 命令（符号搜索、调用图、依赖图） | 浏览生成的 Markdown 页面 | Web UI + 聊天助手 + MCP |
| **图算法** | ✅ 调用图 BFS、依赖图 BFS | ❌ 无 | ❌ 思维导图 |
| **支持语言** | TypeScript / JS（Python 规划中） | 14 种（TS、JS、Vue、Go、Python、Rust 等） | 任意（AI 理解） |
| **增量更新** | ❌ 全量重建 | ✅ AST 哈希缓存 | ✅ 定时增量 worker |
| **需要 LLM** | ❌ 完全不需要 | ✅ 需要（75+ 提供商） | ✅ 需要 |
| **运行成本** | 免费 | ~$0.05-$0.20 / 次 | API 费用 + 托管费用 |
| **代码离开本机？** | ❌ 完全本地 | ❌ 仅发送给 LLM 提供商 | ❌ 仅发送给 LLM 提供商 |
| **输出格式** | SQLite + CLI 结果 + Mermaid | Markdown + Mermaid | Markdown + Web 页面 + 思维导图 |
| **独特优势** | 符号级调用图、零云依赖、完全免费 | 并行 Agent、差异感知同步、Agent SDK | 公共文档托管、RBAC、MCP 端点 |

**简单说：**

- **CodeAtlas** 是静态分析优先的工具 — 不需要 LLM，不需要 API Key，完全离线。你得到的是一张精确的、可查询的代码知识地图。
- **ZRead** 是 AI 驱动的 Wiki 生成器 — 用并行 Agent 生成人类可读的文档页面，适合团队入职和代码审查，但需要 LLM API 费用。
- **DeepWiki** 侧重公共文档托管和团队协作 — 提供 Web UI、聊天助手和 MCP 端点，定位更接近企业级文档平台。

**三者不是替代关系，而是互补关系。** 很多用户的实际工作流是：

```
用 CodeAtlas 做精确的符号查询和调用追踪
    ↓
把 CodeAtlas 的输出喂给 Claude Code / Codex
    ↓
用 ZRead 或 DeepWiki 生成团队 Wiki
```

### 与代码搜索工具的比较

| 特性 | CodeAtlas | Cursor | Sourcegraph |
|-------|-----------|--------|-------------|
| 本地优先 | ✅ | ❌ | ❌ |
| SQLite 索引 | ✅ | ❌ | ❌ |
| 架构报告 | ✅ | 有限 | ❌ |
| 调用图遍历 | ✅ | 部分 | ✅ |
| 依赖图 | ✅ | ❌ | ✅ |
| Mermaid 导出 | ✅ | ❌ | ❌ |
| 需要 LLM | ❌ | ✅ | ❌ |
| tsconfig 别名支持 | ✅ | ❌ | ❌ |
| 离线 / 无需网络 | ✅ | ❌ | ❌ |
| 永久免费 | ✅ | 付费 | 付费层级 |

---

## 常见问题

### 我的代码会发送到云端吗？

不会。所有内容都存储在本地 `~/.codeatlas/projects/<name>/index.db`。不需要网络连接。

### 需要 OpenAI 或任何 LLM 吗？

不需要。CodeAtlas 完全离线运行，是一个独立的 CLI 工具。

### 我能在提示 GPT/Claude 之前用它吗？

可以。很多用户先运行 CodeAtlas，然后把输出（调用链、依赖图、架构报告）粘贴到 LLM 会话中，获得更丰富的上下文。

### 支持哪些语言？

目前：**TypeScript、TSX、JavaScript、JSX**。Python 支持已在规划中。

### 数据存在哪里？

每个索引项目拥有自己的 SQLite 数据库，位于 `~/.codeatlas/projects/<project-name>/index.db`。数据库使用 WAL 模式保证并发读取安全。

### 可以重复索引同一个项目吗？

可以 — 再次运行 `codeatlas index` 会覆盖之前的索引。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 编程语言 | Python 3.11+ |
| CLI 框架 | Click |
| AST 解析器 | tree-sitter-languages (TSX) |
| 存储 | SQLite3（WAL 模式） |
| 图算法 | 可配置深度的 BFS |
| 图表输出 | Mermaid TD 语法 |

---

## 路线图

- [ ] Python 解析器支持
- [ ] 增量索引（仅变更文件）
- [ ] 查询索引的 Web UI
- [ ] 符号重命名 / 重构安全检查
- [ ] 导入循环检测
- [ ] 编程访问 API（Python SDK）

---

## 许可证

MIT
