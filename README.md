# 招聘数据分析平台

从数据采集到 AI Agent 的完整链路课程项目。

## 项目结构

```
project1/
├── app.py                    # Flask 入口 (Web 服务 + 路由)
├── config.py                 # 配置 (数据库路径、API Key)
├── data/                     # 数据采集与清洗
│   ├── python_job_scraper.py    — 51job 实时采集 (Playwright)
│   ├── salary_parser.py         — 薪资字符串解析
│   └── fix_duplicate_address.py — 地址清洗
├── analysis/                 # 描述性统计
│   ├── xinzi.py                 — 薪资分布
│   ├── xueli.py                 — 学历分布
│   ├── jinyan.py                — 经验分布
│   ├── region.py                — 城市分布 (含 extract_city 共享工具)
│   └── jobtitle.py              — 职位分类 (规则引擎)
├── modeling/                 # 机器学习模型
│   ├── job_clustering.py        — KMeans 无监督聚类
│   ├── salary_predict.py        — 线性回归薪资预测
│   └── cache.py                 — 模型缓存 (单一真相来源)
├── agent/                    # ReAct Agent
│   ├── agent_core.py            — 推理循环 (Reason + Act)
│   └── agent_tools.py           — 工具注册 + 查询函数
├── templates/                # HTML 模板
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker 一键部署
├── .dockerignore             # Docker 忽略文件
├── test_*.py                 # 测试文件
└── deprecated/               # 历史代码备份
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

**核心原则**：下层模块不依赖上层。`agent/tools.py` 的 `city_overview` 复用 `analysis/region.extract_city()`；`modeling/salary_predict.py` 复用 `analysis/jobtitle.classify()`。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 配置 API Key (可选，仅 Agent 功能需要)
# 在项目根目录创建 .env 文件，写入: DEEPSEEK_API_KEY=你的Key

# 3. 启动 Web 服务
python app.py
# 访问 http://127.0.0.1:5000

# 4. 命令行独立运行各模块
python -m analysis.xinzi        # 薪资分布
python -m analysis.jobtitle     # 职位分类
python -m modeling.job_clustering  # 聚类分析
python -m modeling.salary_predict  # 薪资预测
python -m data.fix_duplicate_address  # 地址清洗
python test_agent_loop.py       # Agent 逻辑测试
```

## Docker 部署

```bash
# 方式一: docker-compose (推荐)
docker-compose up -d
# 访问 http://localhost:5000

# 方式二: 手动构建
docker build -t job-analysis .
docker run -d -p 5000:5000 \
  -v $(pwd)/data.db:/app/data.db \
  --env-file .env \
  job-analysis

# 虚拟机部署 (需要 Python 3.10+)
git clone <repo-url> && cd project1
pip install -r requirements.txt
playwright install chromium     # 采集数据需要
python app.py                   # 访问 http://<vm-ip>:5000
```

## Web 页面

| 路由 | 功能 | 页面 |
|------|------|------|
| `/` | 首页 (数据采集入口) | `input.html` |
| `/list` | 职位列表 (分页+筛选) | `data.html` |
| `/chart` | 薪资/学历/经验分布 | `h.html` |
| `/ml` | 聚类结果 + 薪资预测 | `ml.html` |
| `/advice` | AI Agent 问答 | `advice.html` |
| `/collect` | 触发实时采集 | `collect.html` |

## 课程阅读顺序建议

1. `config.py` — 了解配置
2. `data/` — 数据从哪来、怎么清洗
3. `analysis/` — 基础统计怎么做
4. `modeling/` — 聚类和回归模型
5. `agent/` — Agent 怎么把工具组合起来
6. `app.py` — 所有部分怎么串成 Web 应用
