# EverMind v2 重设计方案

> 状态：草案 · 日期：2026-07-08

---

## 1. 现状诊断：慢、繁琐、配置难的根源

通过完整阅读 `mcp/src/evermind_mcp/` 全部源码，以下是三个核心问题的技术根因。

### 1.1 运行慢

| 操作 | 当前延迟 | 根因 |
|------|----------|------|
| `remember()` | 200ms–5s | 走本地 HTTP → EverOS 进程 → 再调外部 LLM API 提取 |
| `recall()` auto 模式 | 300ms–3s | 2 次并发 HTTP；multi-space 触发最多 N 个探针请求 |
| `briefing()` | 500ms–1s | 多次 fetch_memories() 并发 HTTP |
| 配置启动时 | 直接报错 | EverOS 进程未启动，MCP 尝试连接 127.0.0.1:3378 失败 |

**根本原因**：EverMind 依赖一个单独的 EverOS HTTP 服务（3378 端口），所有读写都走本地 HTTP 调用。这是在本地加了一层不必要的网络层，延迟是纯磁盘操作的 10–100 倍。

当前架构：
```
Agent → MCP Server (Python) → HTTP → EverOS 进程 (3378) → LLM API (外网)
```

### 1.2 工作流繁琐

保存一个重要发现到长期记忆需要三步：

1. 调用 `remember(content, space_id="coding:my-app")` → 等待
2. 调用 `propose_archive_update(evidence=..., reason=...)` → 等待  
3. 用户手动确认 → 调用 `commit_archive_update(candidate_id=..., confirmed=true)`

9 个 MCP 工具，Agent 不清楚该用哪个。`briefing` 和 `recall` 都要手动调。
`request_status` 需要轮询等待 LLM 提取完成。

### 1.3 配置复杂导致 Claude/Cursor 报错

当前 mcp-config.json 有 3 个必须手动替换的占位符：

- `<EVERMIND_ROOT>` — EverMind 仓库路径
- `<EVEROS_ROOT>` — EverOS 存储路径  
- `<EVERMIND_ARCHIVE_ROOT>` — Archive 路径

加上 .env 中 20+ 个变量（LLM 模型、embedding 模型、rerank 模型、API key、路径）。
任何一个缺失或路径格式错误都会导致 Claude Desktop / Cursor 报 MCP 连接错误。

### 1.4 记忆准确度低

- 多 space 搜索时 space_id 丢失 → 触发并发探针补救（最多 N 次额外 HTTP）
- 无写入时去重，同一内容多次 remember 会重复堆积，污染召回结果
- 姓名/偏好提取靠硬编码正则，仅支持中英文
- Archive 文件名硬编码中文（项目概览.md 等），多语言用户无法使用

---

## 2. 设计原则（v2）

| 原则 | 含义 |
|------|------|
| **零外部依赖** | 不依赖任何额外进程；单个 Python 包即可运行 |
| **写入立即完成** | 写入操作 < 20ms，LLM 提取在后台异步进行 |
| **最少工具** | 3 个核心工具覆盖 95% 使用场景 |
| **零配置启动** | 从 git remote 自动推断项目名，无需任何 env var |
| **相似内容自动合并** | 写入时检测相似度，自动合并而非重复堆积 |
| **平台无关** | Claude Desktop、Cursor、Codex 同一套配置 |

---

## 3. 新架构总览

```
新架构（v2）：

Agent
  |
  v
MCP Server (Python, 单进程，无外部依赖)
  |
  |-- 同步写入 (< 20ms)
  |     +-- SQLite (本地单文件)
  |           |-- FTS5 全文索引
  |           +-- sqlite-vec 向量索引
  |
  +-- 异步后台 (非阻塞)
        |-- 本地 embedding 模型 (sentence-transformers，可选)
        +-- LLM 事实提取 (有 API key 时启用，可选)
```

关键变化：去掉 EverOS 进程，MCP Server 直接内嵌 SQLite 数据库。
所有读写变成本地磁盘操作，无 HTTP 开销。

---

## 4. 存储层：SQLite Embedded

### 4.1 技术选型对比

| 方案 | 零额外进程 | 向量搜索 | 全文搜索 | 安装复杂度 |
|------|-----------|---------|---------|----------|
| **SQLite + sqlite-vec** | 是 | KNN | FTS5 | pip install sqlite-vec |
| LanceDB | 是 | 是 | 有限 | pip install lancedb |
| ChromaDB | 否，需服务 | 是 | 否 | 较重 |
| 当前 EverOS | 否，独立进程 | 是 | 是 | 需单独部署 |

sqlite-vec 是 SQLite 官方作者开发的向量扩展，支持 SIMD 加速 KNN，Python 零配置安装。
结合 SQLite 内置 FTS5，一个文件完成关键词 + 语义双路召回。

### 4.2 数据库 Schema

```sql
-- 记忆主表
CREATE TABLE memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    space       TEXT NOT NULL,
    role        TEXT DEFAULT 'user',
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    importance  INTEGER DEFAULT 0,   -- 0=普通 1=重要 2=持久化
    tags        TEXT,                -- JSON array
    meta        TEXT                 -- JSON 扩展字段
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content, tags,
    content='memories', content_rowid='rowid',
    tokenize='unicode61'
);

-- 向量表（sqlite-vec）
CREATE VIRTUAL TABLE memory_vecs USING vec0(
    memory_id TEXT,
    embedding FLOAT[384]
);

-- 提取的事实（原子化知识，可选）
CREATE TABLE facts (
    id          TEXT PRIMARY KEY,
    memory_id   TEXT REFERENCES memories(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    confidence  REAL DEFAULT 1.0,
    created_at  INTEGER NOT NULL
);

-- 会话简报缓存（预物化，session start 毫秒级加载）
CREATE TABLE briefing_cache (
    space       TEXT PRIMARY KEY,
    summary     TEXT NOT NULL,
    top_facts   TEXT NOT NULL,       -- JSON
    updated_at  INTEGER NOT NULL
);
```

### 4.3 存储路径（自动推断）

```
Windows:  %USERPROFILE%\.evermind\<project-slug>.db
macOS:    ~/.evermind/<project-slug>.db

<project-slug> 从 git remote URL 自动推断：
  git@github.com:user/evermind.git  →  evermind
  https://github.com/org/my-app.git →  my-app
  无 git remote                     →  default
```

---

## 5. 工具层：3 个工具替代 9 个

### 当前 9 个工具（问题）

list_spaces · remember · request_status · recall · briefing · forget ·
fetch_history · propose_archive_update · commit_archive_update

Agent 不清楚何时调 briefing 还是 recall，不知道何时轮询 request_status，
保存重要内容要走三步。

### v2 核心 3 个工具

#### `remember(content, importance=0, tags=[])`

存储一条记忆。立即返回（< 20ms），异步建索引。

- importance=0：普通工作记忆，可被淘汰
- importance=1：重要，长期保留
- importance=2：持久化，永不自动删除（替代原 propose/commit 三步流程）

若检测到相似度 > 0.92 的已有记忆，自动合并更新，返回 similar_merged: true。

#### `recall(query, limit=10, mode="hybrid")`

混合搜索：BM25（FTS5）+ 向量 KNN，用 RRF 倒数排名融合合并结果。

- 自动从 git 推断当前项目空间，无需传 space_id
- mode 可选 keyword / semantic / hybrid（默认）
- 若 embedding 尚未建好，降级为纯 FTS5，不报错

#### `forget(id)`

删除一条记忆，级联删除向量和事实，立即生效。

### 会话开始：自动加载简报

不再需要手动调 briefing。MCP 服务启动时通过 MCP Resource 机制
自动读取 briefing_cache 注入上下文，Agent 开始工作时记忆已就位。

### 辅助工具（不影响主流程）

- `status()` — 数据库统计：记忆数、embedding 进度
- `export(format="markdown")` — 导出为 Markdown（替代原 Archive）

---

## 6. 写入路径（< 20ms 同步返回）

```
remember(content) 调用
    |
    +-- Step 1: 写入 memories 表 (SQLite INSERT, ~2ms)
    +-- Step 2: 写入 memories_fts (FTS5 触发器, ~1ms)
    +-- Step 3: BM25 快速去重检查 (~5ms)
    |           若相似度 > 0.92 -> 合并，不新增
    |
    +-- 立即返回 {id, stored_at}   <- 总耗时 < 20ms
    |
    +-- [后台异步，不阻塞返回]
          +-- 生成 embedding -> 写入 memory_vecs (~50-300ms)
          +-- 提取事实三元组 -> 写入 facts (~1-5s，需 LLM，可选)
          +-- 更新 briefing_cache (~100ms)
```

对比当前：remember() 同步等待 EverOS HTTP + LLM 提取，最慢 5s。
v2 同步路径只有本地 SQLite 写入，< 20ms 固定返回。

---

## 7. 读取路径（< 30ms）

```
recall(query) 调用
    |
    +-- 并行执行：
    |     +-- FTS5 BM25 全文搜索 (~5ms)
    |     +-- sqlite-vec KNN 向量搜索 (~10-20ms，若 embedding 已建好)
    |
    +-- RRF 融合排名 (~1ms)
    |     score = 1/(k+rank_fts) + 1/(k+rank_vec)，k=60
    |
    +-- 返回 top-k 结果，附相关性分数
```

刚写入但 embedding 尚未建好的记忆，FTS5 仍能召回，不会出现"刚存的记忆搜不到"的问题。

---

## 8. 配置方案：从 20+ 变量到零配置

### v2 Claude Desktop 配置（最简）

```json
{
  "mcpServers": {
    "evermind": {
      "command": "uvx",
      "args": ["evermind-mcp"]
    }
  }
}
```

uvx 自动从 PyPI 安装最新版并运行，无需 clone 仓库、无需填路径占位符。
项目空间从 Claude 当前工作目录的 git remote 自动推断。

### v2 Cursor 配置

完全相同，两行。Cursor 打开不同项目时，MCP server 自动切换到对应项目的 SQLite 文件。

### 可选环境变量（仅高级用户）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| EVERMIND_HOME | ~/.evermind | 数据库存放目录 |
| EVERMIND_EMBED_MODEL | all-MiniLM-L6-v2 | 本地 embedding 模型 |
| EVERMIND_LLM_API_KEY | 无 | 有此 key 时启用 LLM 事实提取 |
| EVERMIND_LLM_MODEL | gpt-4o-mini | LLM 提取用模型 |

不设置任何变量时，以纯本地模式运行（FTS5 关键词搜索），无需任何 API key。

---

## 9. Embedding 策略

### 离线本地模型（默认）

使用 sentence-transformers + all-MiniLM-L6-v2（22MB，384 维）：
- 首次运行自动下载，之后完全离线
- CPU 推理约 30–80ms/条（Intel i7）

中文场景推荐替换为 BAAI/bge-small-zh-v1.5（同样 22MB，专为中文优化）：
  EVERMIND_EMBED_MODEL=BAAI/bge-small-zh-v1.5

### 云端 Embedding（可选）

设置 EVERMIND_EMBED_API_KEY 后自动切换为 API 调用（兼容 OpenAI 接口），
写入后台任务仍非阻塞，不影响 < 20ms 的同步返回。

---

## 10. 性能对比

| 操作 | 当前 v1 | 目标 v2 | 提升 |
|------|---------|---------|------|
| remember() 返回 | 200ms–5s | < 20ms | 10–250x |
| recall() 单空间 | 300–800ms | < 30ms | 10–27x |
| recall() 多空间 | 1–3s | < 30ms | 33–100x |
| 会话开始加载上下文 | 500ms–1s | < 5ms（缓存读） | 100–200x |
| 保存长期记忆 | 3 步骤手动确认 | 1 步骤（importance=2） | 3x 简化 |
| MCP 配置 | 3 占位符 + 20 env var | 0 配置 | 彻底简化 |
| 配置报错概率 | 高（EverOS 未启动） | 极低（内嵌，无外部依赖） | — |

---

## 11. 迁移方案

### 数据迁移命令

```bash
uvx evermind-mcp migrate --from-everos <EVEROS_ROOT>
```

自动读取当前 EverOS 本地存储（Markdown 文件 + LanceDB 索引）并导入到 SQLite。

### Agent 指令简化

原来 CLAUDE.md 中复杂的工作流说明，v2 简化为：

```markdown
## EverMind Memory

会话开始时记忆自动加载，无需手动调 briefing。

- 搜索相关记忆：recall(query)
- 保存有用信息：remember(content)
- 重要架构决策需永久保留：remember(content, importance=2)
```

---

## 12. 实施路线图

### Phase 1：核心存储替换（优先级最高，约 2 周）

- [ ] 实现 EmbeddedStorage 类（SQLite + sqlite-vec）
- [ ] 实现 3 个核心工具（remember / recall / forget）
- [ ] git remote 自动推断 space
- [ ] uvx 零配置启动支持
- [ ] 单元测试覆盖写入 / 搜索 / 去重

交付：可用的 v2 MCP server，Claude Desktop 两行配置即可运行。

### Phase 2：后台提取与缓存（约 1 周）

- [ ] 异步 embedding 队列
- [ ] 本地 sentence-transformers 集成
- [ ] briefing_cache 预物化
- [ ] status() 工具展示 embedding 进度

交付：向量语义搜索生效，会话开始 < 5ms 加载上下文。

### Phase 3：事实提取与图谱（可选增强，约 2 周）

- [ ] LLM 事实提取管道（有 API key 时启用）
- [ ] facts 表和实体关系查询
- [ ] export(format="markdown") Archive 导出

### Phase 4：平台验证（约 1 周）

- [ ] Claude Desktop（Windows + macOS）端到端测试
- [ ] Cursor 集成测试
- [ ] 数据迁移工具

---

## 13. 关键技术依赖

| 库 | 用途 | 说明 |
|----|------|------|
| sqlite-vec | 向量 KNN 搜索 | SQLite 扩展，零进程，pip install sqlite-vec |
| sentence-transformers | 本地 embedding | 可选，首次运行自动下载 |
| mcp | MCP 协议 | 保持不变，>=1.0 |
| httpx | LLM API 调用 | 仅事实提取用，可选 |

移除：everos_client.py、cloud_client.py、space_catalog_service.py

---

## 参考资料

- sqlite-vec 向量扩展：https://github.com/asg017/sqlite-vec
- Memento MCP（SQLite+FTS5+sqlite-vec 方案参考）：https://mcp.so/server/memento/iAchilles
- Mem0 论文（原子事实提取架构）：https://arxiv.org/abs/2504.19413
- Mem0 图记忆（91% 更快响应）：https://mem0.ai/blog/graph-memory-solutions-ai-agents
- 超越向量数据库的长期记忆架构：https://vardhmanandroid2015.medium.com/beyond-vector-databases-architectures-for-true-long-term-ai-memory-0d4629d1a006
