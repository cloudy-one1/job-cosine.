# 招聘数据分析与可视化系统

一个基于 Python 的招聘市场数据分析全栈项目，提供从数据采集、存储、分析到可视化展示的完整流程，并集成了基于大语言模型的智能问答功能。

## 核心功能

| 模块 | 功能 | 技术 |
|------|------|------|
| 数据采集 | 51job 实时职位抓取 | Playwright (Chrome 无头) + stealth 对抗 WAF |
| 数据清洗 | 薪资解析、地址去重 | 正则 + 规则引擎 |
| 描述性统计 | 薪资/学历/经验/城市分布 | Pandas + SQLite |
| 职位聚类 | 自动发现职位类别结构 | Jieba 分词 + TF-IDF + KMeans + 轮廓系数 |
| 薪资预测 | 多维特征线性回归 | Scikit-Learn + OneHotEncoder |
| AI Agent | 自然语言交互式数据分析 | 手写 ReAct 推理循环 + LLM 工具调用 |
| Docker 部署 | 一键容器化运行 | Docker + docker-compose |

> **容错设计**：空数据库首次启动不会崩溃，所有页面友好提示"请先采集数据"，无需预先准备任何数据。

## 项目结构

```
project1/
├── app.py                    # Flask 入口 (Web 服务 + 路由)
├── config.py                 # 配置 (数据库路径、API Key 从 .env 读取)
│
├── data/                     # 数据层：采集 + 清洗
│   ├── python_job_scraper.py    — 51job 实时采集 (Playwright + stealth)
│   ├── salary_parser.py         — 薪资字符串解析 (1.5-2万/月 → 千元数值)
│   └── fix_duplicate_address.py — 地址去重与清洗
│
├── analysis/                 # 分析层：统计 + 可视化数据生成
│   ├── xinzi.py                 — 薪资分布统计
│   ├── xueli.py                 — 学历分布统计
│   ├── jinyan.py                — 经验分布统计
│   ├── region.py                — 城市分布统计 (含 extract_city 共享工具)
│   └── jobtitle.py              — 职位标题规则分类
│
├── modeling/                 # 模型层：机器学习
│   ├── job_clustering.py        — KMeans 无监督聚类 (自动选择最佳 k)
│   ├── salary_predict.py        — 线性回归薪资预测 (基线 vs 全特征对比)
│   └── cache.py                 — 模型结果缓存 (单一真相来源)
│
├── agent/                    # Agent 层：大模型对话
│   ├── agent_core.py            — 手写 ReAct 推理循环 (Reason + Act)
│   └── agent_tools.py           — 工具注册与查询函数 (6 个可调用工具)
│
├── templates/                # HTML 模板 (7 个页面)
│   ├── base.html, input.html, data.html
│   ├── h.html, ml.html, advice.html
│   └── collect.html
│
├── tests/                    # 测试
│   ├── test_agent_loop.py       — Agent 逻辑集成测试 (假 LLM 存根)
│   └── test_python_job_scraper.py — 采集参数构建单元测试 (22 个用例)
│
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker 一键部署
├── .dockerignore             # Docker 忽略文件
│
├── .env.example              # 环境变量示例 (复制为 .env 填入 Key)
├── requirements.txt          # 依赖清单
└── README.md                 # 本文件
```

## 分层依赖关系

```
templates + app.py    ← 展示层
        ↓
agent/                ← Agent 层 (复用分析层+建模层)
        ↓
modeling/             ← 建模层 (依赖分析层的 classify / extract_city)
        ↓
analysis/             ← 描述性统计层 (依赖 config + data.db)
        ↓
data/                 ← 数据层 (采集、解析、清洗)
        ↓
config.py + data.db   ← 基础设施
```

**核心原则**：下层模块不依赖上层。`agent/agent_tools.py` 的 `city_overview` 复用 `analysis/region.extract_city()`；`modeling/salary_predict.py` 复用 `analysis/jobtitle.classify()`。

## 快速开始

### 方式一：本地直接运行（推荐用于开发/演示）

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 配置 API Key (可选，仅 Agent 功能需要)
# 复制 .env.example 为 .env，写入: DEEPSEEK_API_KEY=你的Key

# 3. 启动 Web 服务
python app.py
# 访问 http://127.0.0.1:5000

# 4. 命令行独立运行各模块验证
python -c "from analysis.xinzi import salary_distribution; print(salary_distribution())"
python -c "from analysis.jobtitle import classify_batch; print(classify_batch())"
python -c "from modeling.job_clustering import run_clustering; print(run_clustering())"
python -c "from modeling.salary_predict import train_and_evaluate; print(train_and_evaluate())"
python -c "from data.fix_duplicate_address import fix_addresses; print(fix_addresses())"
python -m pytest tests/ -v   # 运行全部测试 (27 个用例)
```

### 方式二：Docker 部署（推荐用于服务器/长期运行）

> **架构分工**：数据采集（Playwright + Chromium）依赖真实浏览器指纹对抗 WAF，因此在宿主机本地执行后写入 `data.db`；Docker 容器仅负责 Web 展示 + 模型推理 + Agent，通过 volume 挂载共享同一个 SQLite 数据库。镜像体积约 300MB（不含 Chromium）。

```bash
# 1. 先在本地采集一次数据 (Playwright 需要真实浏览器指纹)
python -c "from data.python_job_scraper import scrape_jobs; scrape_jobs()"

# 2. 启动 Docker 容器 (纯 Web 服务，不含爬虫)
# 方式一: docker-compose (推荐，最简单)
docker-compose up -d
# 访问 http://localhost:5000

# 方式二: 手动构建与运行
docker build -t job-analysis .
docker run -d -p 5000:5000 \
  -v $(pwd)/data.db:/app/data.db \
  --env-file .env \
  job-analysis

# 后续更新数据：宿主机重新采集，无需重启容器 (共享 data.db)
```

#### 镜像源配置（国内网络环境）

若 Docker Hub 连接超时，在 Docker Desktop → Settings → Docker Engine 中添加镜像源：

```json
"registry-mirrors": [
  "https://docker.1ms.run",
  "https://docker.xuanyuan.me"
]
```

#### 虚拟机/服务器部署（需要 Python 3.10+）

```bash
git clone <你的仓库地址>
cd project1
pip install -r requirements.txt
playwright install chromium      # 仅在需要采集的机器上安装
python app.py                      # 访问 http://<服务器IP>:5000
```

## Web 页面说明

| 路由 | 功能 | 模板文件 |
|------|------|---------|
| `/` | 首页（关键词 + 城市输入） | `input.html` |
| `/list` | 职位列表（分页 + 筛选） | `data.html` |
| `/chart` | 薪资/学历/经验分布图 | `h.html` |
| `/ml` | 聚类结果 + 薪资预测表单 | `ml.html` |
| `/advice` | AI Agent 问答对话 | `advice.html` |
| `/collect` | 触发实时数据采集 | `collect.html` |

## 代码阅读建议（课程学习顺序）

1. **`config.py`** — 了解项目的基础配置（数据库路径、LLM API Key）
2. **`data/`** — 数据从哪来、怎么清洗（Playwright 采集 → 薪资解析 → 地址去重）
3. **`analysis/`** — 基础统计怎么做（薪资/学历/经验/城市分布 + 职位规则分类）
4. **`modeling/`** — 聚类（KMeans + 轮廓系数选择 k）和回归预测（线性回归 + OneHot 编码）
5. **`agent/`** — Agent 如何把工具组合起来回答问题（手写 ReAct 推理循环 + 6 个工具注册）
6. **`app.py`** — 所有部分怎样串成一个完整的 Web 应用（路由 + 空库容错 + 模型缓存）

## Git 提交规范

- `feat:` 新增功能
- `fix:` 修复 Bug
- `refactor:` 代码重构（不改变功能）
- `docs:` 文档更新
- `cleanup:` 清理/删除无用代码
- `perf:` 性能优化
