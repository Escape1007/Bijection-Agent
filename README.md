# Bijection Proof Agent

专门辅助组合数学中双射/对合证明的 AI Agent。

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Key：

```env
MODEL_PROVIDER=deepseek        # deepseek / openai / claude / glm
DEEPSEEK_API_KEY=sk-xxxxx      # 填入你的 key
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行

```bash
python main.py                    # 进入交互式 REPL
python main.py --query "..."      # 单次问答，跑完打印完整轨迹后退出
python main.py --model deepseek-v4-flash   # 覆盖模型（默认 AGENT_MODEL env）
```

启动时自动校验 API Key、加载知识库（`data/chroma_agent/`）并打印条目数。

### REPL 命令

```
/help        显示帮助
/status      显示知识库状态（entries / docs）
/quit, /exit 退出
```

其他输入直接作为双射问题发给 agent。

## Agent 能力

- **检索**：`search_bijections` 查询本地知识库（5 个种子双射 + arXiv 试点入库的
  22 条），按 search_intent 路由到 identity / method / proof_strategy /
  technique_abstraction 四层粒度。
- **验证**：`verify_bijection` 三层兜底——SageMath（WSL，需 WSL 内安装 sage）→
  纯 Python（Dyck 路径 / 置换 / 划分 / 二叉树）→ 理论证明。
- **推理**：ReAct 循环，系统提示含 S1–S10 构造策略与四阶段推理流。

## 支持的模型

| 编号 | 模型 | 说明 |
|------|------|------|
| 1 | DeepSeek | 默认，性价比最高 |
| 2 | OpenAI | GPT 系列 |
| 3 | Claude | Anthropic，推理能力强 |
| 4 | GLM | 智谱清言 |

所有模型均使用其最强推理强度配置。