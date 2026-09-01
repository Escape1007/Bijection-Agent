# data/arxiv — T2b arXiv 爬取数据

## 目录结构

```
data/arxiv/
├── README.md           # 本文件
├── status.json         # 论文状态记录（机器可读，爬虫自动维护）
├── sources/            # 原始下载（tar.gz / 解压后的单 tex）
│   └── <arxiv_id>.tar.gz|.tex
└── expanded/           # 展平后的单文件 LaTeX（\input/\include 已展开）
    └── <arxiv_id>.tex
```

## 状态机制（对齐 arxiv-to-prompt 的缓存语义）

爬虫 `src/crawler/arxiv_crawler.py` 维护 `status.json`，键为 **arXiv 基础 id**
（不含版本号）。每篇论文的状态：

- `status: "downloaded"` —— 已下载并展平，缓存于本地，**重复运行直接复用**。
- `status: "failed"` + `failure_kind: "permanent"` —— 永久失败（无 LaTeX 源码、
  源码包损坏等），**重复运行跳过**。
- `status: "failed"` + `failure_kind: "transient"` —— 暂时性失败（网络超时、
  HTTP 5xx），**重复运行自动重试**。

与 arxiv-to-prompt 的差异：除"成功缓存复用"外，额外持久化了失败论文及原因，
且区分永久/暂时性失败（对应 `paper_collector常用命令.md` 中"跳过已下载/永久失败，
优先重爬暂时性失败"的约定）。强制重爬用 `--force-download`。

## 当前批次（2026-08-19）

- 查询：`au:"Shishuo_Fu" AND cat:math.CO`
- 命中 **42 篇**，全部成功下载并展平（`sources/` 与 `expanded/` 各 42 个文件）。
- 失败：0。

## 常用命令

```
python src/crawler/arxiv_crawler.py --dry-run        # 只搜索，列出论文与状态
python src/crawler/arxiv_crawler.py                  # 全量（跳过已下载/永久失败，重试暂时性失败）
python src/crawler/arxiv_crawler.py --force-download # 强制全部重新下载
python src/crawler/arxiv_crawler.py --stats          # 状态统计
```

## 数据来源与质量

- 源码端点：`https://arxiv.org/e-print/<arxiv_id>`（LaTeX 源码，优先于 PDF——
  数学论文 RAG 的最佳输入，见 `对齐重要需求及回答记录/GitHub开源项目调研.md`）。
- 单文件 gzip 论文在下载阶段原地解压为 `.tex`；tar.gz 包解压后定位主 `.tex`
  （含 `\documentclass`），递归展开 `\input`/`\include`（深度上限 12，防循环）。
- 下一环节（T2b 入库，已实现）：`src/knowledge/arxiv_ingest.py` 对 `expanded/*.tex`
  提取定理环境（正则，含 `\newtheorem` 自定义环境名）→ 关键词筛双射候选 →
  DeepSeek 精提 4 层文本 → 双模型（math-embed + BGE-M3）写入
  `data/chroma_agent/`（collection `bijections_agent` / `bijections_agent_bgem3`），
  `data/contexts/{entry_id}.json` 为模型无关真源。
  命令：`python -m src.knowledge.arxiv_ingest --arxiv-id <id> [--dry-run] [--limit N]`。
  检索对比：`python scripts/compare_embeddings.py`。
