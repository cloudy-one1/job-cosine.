# 招聘数据分析与可视化系统

一个基于 Python 的招聘市场数据分析全栈项目。提供从数据采集、存储、分析到可视化展示的完整流程，并集成了基于大语言模型的智能问答功能。

## 功能特性

- 🔍 **实时数据采集** — 使用 Playwright + stealth 技术绕过 51job 的 WAF 防护，采集真实招聘职位
- 💾 **本地数据管理** — 基于 SQLite 数据库存储，支持 CSV 批量导入与实时采集两种获取方式
- 📊 **多维度统计分析**
  - 薪资分布（分桶区间可视化）
  - 学历要求分布
  - 工作经验要求分布
  - 城市 / 地区热度排行
  - 职位分类（基于关键词规则）
- 🧩 **无监督聚类分析** — 使用 jieba 中文分词 + TF-IDF + KMeans 聚类，自动发现职位标题的语义分组
- 💰 **薪资预测模型** — 基于线性回归，输入城市、职位类别、学历、经验即可预测月薪水平
- 🤖 **AI 求职助手** — 手写实现的 ReAct Agent 循环，调用 DeepSeek API，可基于本地数据回答各类就业相关问题
- 🌐 **Flask Web 界面** — 提供列表浏览、图表展示、ML 分析、实时采集、AI 问答等完整页面

## 技术栈

| 模块 | 技术 |
|------|------|
| Web 框架 | Flask |
| 数据库 | SQLite |
| 数据采集 | Playwright + playwright-stealth |
| 数据处理 | pandas |
| 中文分词 | jieba |
| 向量化 | scikit-learn TF-IDF |
| 聚类 | scikit-learn KMeans |
| 预测模型 | scikit-learn 线性回归 + OneHotEncoder |
| AI Agent | DeepSeek API（ReAct 模式） |

## 项目结构

```
project1/
├── app.py                 # Flask 主程序（路由与页面渲染）
├── config.py              # 配置文件（API Key 从 .env 读取）
├── python_job_scraper.py  # 51job 实时数据采集（参数化调用）
├── salary_parser.py       # 薪资字符串解析工具（如 "1.5-2万/月" → (15.0, 20.0) 千元）
├── job_clustering.py      # 职位标题无监督聚类
├── salary_predict.py      # 薪资预测线性回归模型
├── xinzi.py               # 薪资分布统计
├── xueli.py               # 学历分布统计
├── jinyan.py              # 经验分布统计
├── region.py              # 地区分布统计
├── jobtitle.py            # 职位标题规则分类
├── agent_core.py          # ReAct Agent 循环核心
├── agent_tools.py         # Agent 可用工具集
├── templates/             # HTML 模板
├── deprecated/            # 已迁移 / 不再推荐使用的旧文件（保留参考）
│   ├── import_fresh_data.py
│   ├── fresh_job_data.csv
│   └── advice_route_snippet.py
├── .env.example           # 环境变量示例（复制为 .env 后填入自己的 Key）
├── requirements.txt       # 依赖清单
└── README.md              # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key（可选，用于 AI 助手功能）

```bash
# 复制示例文件
cp .env.example .env
```

编辑 `.env`，填入你的 DeepSeek API Key：

```
DEEPSEEK_API_KEY=你的_api_key_在这里
```

> 如果不配置 AI 助手，也可以正常使用其他所有功能（数据采集、统计、聚类、预测）。

### 3. 准备数据（二选一）

**方式 A：从 51job 实时采集**

```bash
python python_job_scraper.py
```

**方式 B：先运行 Web 应用，在网页上点 "实时采集"**

```bash
python app.py
```

然后访问 http://127.0.0.1:5000，在首页输入关键词和城市提交即可。

### 4. 启动 Web 应用

```bash
python app.py
```

打开浏览器访问：**http://127.0.0.1:5000**

## Web 页面路由说明

| 路由 | 说明 |
|------|------|
| `GET /` | 首页，输入采集关键词和城市 |
| `GET /list` | 分页职位列表，支持按关键词和城市过滤 |
| `GET /chart` | 薪资 / 学历 / 经验分布图表 |
| `GET /ml` | 聚类结果 + 规则分类 + 薪资预测展示 |
| `POST /predict` | 根据城市和职位类别预测薪资 |
| `GET\|POST /collect` | 触发一次实时数据采集 |
| `GET\|POST /advice` | 与基于大模型的求职助手对话 |

## 独立使用各模块

每个分析模块都可以单独运行，方便调试或二次开发：

```python
# 职位聚类
from job_clustering import run_clustering
result = run_clustering()
print(f"自动选择的 k 值: {result['k']}")
print(f"聚类结果: {result['clusters'][:3]}")

# 薪资预测
from salary_predict import train_and_evaluate, predict_salary_safe
model_result = train_and_evaluate()
pred, matched_edu, matched_exper, warns = predict_salary_safe(
    model_result['model'], '北京', '数据', '本科', '3-5年',
    model_result['valid_edu'], model_result['valid_exper']
)
print(f"预测月薪: {pred:.1f}K")

# 实时采集
from python_job_scraper import scrape_jobs
jobs = scrape_jobs(keyword='python', cities=['北京', '上海'], pages_per_city=2)
print(f"采集到 {len(jobs)} 条职位")
```

## 核心设计思路

1. **轻量化** — 不依赖复杂的大模型框架，算法透明可见，便于学习和修改
2. **全流程可追溯** — 每个模块可独立运行测试，中间结果可打印检查
3. **模块间通过数据库解耦** — 采集模块写数据库，分析模块读数据库，互不影响
4. **Agent 工具集可扩展** — 在 `agent_tools.py` 里加一个函数，再在 `TOOLS` 字典里注册，就能被大模型调用

## 注意事项

- 本项目仅用于学习研究，请在使用实时采集功能时遵守目标网站的 robots 协议及相关法律法规
- 第一次启动 Flask 时会预计算聚类和薪资预测模型（约几秒），之后页面刷新不会重复计算
- `.env` 和 `data.db` 已在 `.gitignore` 中排除，不会被提交到 GitHub
