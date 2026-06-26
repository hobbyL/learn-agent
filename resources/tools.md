# 工具和库清单

构建 Agent 常用的工具和库。

---

## LLM API

### Claude (Anthropic)
- **官方 SDK**：`pip install anthropic`
- **文档**：https://docs.anthropic.com/
- **特点**：
  - 长上下文（200k tokens）
  - 原生工具调用支持
  - Prompt caching
- **定价**：按 token 计费

### OpenAI
- **官方 SDK**：`pip install openai`
- **文档**：https://platform.openai.com/docs/
- **特点**：
  - GPT-4、GPT-3.5
  - Function calling
  - Assistants API（内置 Agent 功能）

### 本地模型（Ollama）
- **工具**：https://ollama.ai/
- **特点**：
  - 免费本地运行 Llama、Mistral 等模型
  - 无需 API key
  - 适合实验和学习

---

## Agent 框架

### LangChain
- **安装**：`pip install langchain langchain-community`
- **文档**：https://python.langchain.com/
- **核心组件**：
  - `langchain.agents`：Agent 实现
  - `langchain.tools`：工具定义
  - `langchain.memory`：记忆系统

### LlamaIndex
- **安装**：`pip install llama-index`
- **文档**：https://docs.llamaindex.ai/
- **核心组件**：
  - Agent 实现
  - 数据索引和检索

---

## 向量数据库

### Chroma
- **安装**：`pip install chromadb`
- **特点**：轻量级，适合本地开发
- **用途**：长期记忆、RAG

### FAISS
- **安装**：`pip install faiss-cpu`
- **特点**：Facebook 出品，性能高
- **用途**：大规模向量检索

### Pinecone
- **安装**：`pip install pinecone-client`
- **特点**：云服务，免运维
- **用途**：生产环境的向量数据库

---

## 开发工具

### LangSmith
- **用途**：Agent 调试和追踪
- **网站**：https://www.langchain.com/langsmith

### Jupyter Notebook
- **安装**：`pip install jupyter`
- **用途**：交互式开发和实验

### Python REPL
- **安装**：`pip install ipython`
- **用途**：快速测试代码片段

---

## 实用库

### 网络请求
- `requests`：HTTP 请求
- `httpx`：异步 HTTP

### 数据处理
- `pandas`：数据分析
- `numpy`：数值计算

### 日志和监控
- `loguru`：更好的日志库
- `rich`：终端美化输出

### 异步编程
- `asyncio`：Python 内置
- `aiohttp`：异步 HTTP

---

## 环境配置

### 推荐的 Python 版本
- Python 3.10+

### 虚拟环境管理
```bash
# 创建虚拟环境
python -m venv venv

# 激活（macOS/Linux）
source venv/bin/activate

# 激活（Windows）
venv\Scripts\activate
```

### 依赖管理
- `requirements.txt`：简单项目
- `poetry`：复杂项目（`pip install poetry`）

---

## API Key 管理

### 环境变量
```bash
# .env 文件
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

### python-dotenv
```bash
pip install python-dotenv
```

```python
from dotenv import load_dotenv
load_dotenv()
```

---

**最后更新**：2026-06-25
