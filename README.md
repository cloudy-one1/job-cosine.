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
>
> **安全加固**（对抗式审查后修复）：
> - 非法页码输入自动回退，防止 500 崩溃
> - 数据采集采用原子写入，采集中断不会丢失旧数据
> - 数据库异常不再静默吞掉，打印警告日志便于排查
> - 薪资预测对城市/职位类别输入进行验证，未见过的值给出明确警告
> - URL 参数自动转义，防特殊字符截断
> - Agent API 调用带指数退避重试，网络抖动不直接失败
> - 前端异常信息脱敏，不泄露内部路径和堆栈
> - **全站点 CSRF 防护**（Flask-WTF）：3 处 POST 表单强制校验 token，防跨站伪造提交
> - **secret_key 安全注入**：从 `FLASK_SECRET` 环境变量读取，未设时使用 `os.urandom(32)` 随机值
> - **debug/host 默认关闭**：`FLASK_DEBUG` 默认 0，`FLASK_HOST` 默认 `127.0.0.1`，需显式开启才对外暴露
> - 新增 `tests/test_app_routes.py`（10 个用例）覆盖安全修复的回归测试
> - **采集口令保护**：`.env` 配置 `COLLECT_TOKEN` 后，采集需输入口令，防误操作清空数据
> - **速率限制**（Flask-Limiter）：全局 50/小时 + 采集接口 5/小时，防滥用
> - **SQLite WAL 模式**：启动时自动启用，并发读不再被写操作锁库
> - **Agent 参数白名单**：`inspect.signature` 过滤 LLM 幻觉参数，防 TypeError
> - **分页链接 `url_for()`**：自动 URL 编码，杜绝手动拼接的安全隐患
>
> **工程质量**（代码健壮性提升）：
> - **数据库连接管理**：Flask `g` 对象复用连接 + `teardown_appcontext` 自动关闭，避免连接泄漏
> - **模型持久化**：joblib 缓存聚类/回归模型到磁盘 (`cache/`)，服务器重启免重训
> - **日志系统**：`logging` + `RotatingFileHandler` 替代 `print`，分级输出到 `logs/app.log`（5MB 旋转 × 3 备份）
> - **启动性能优化**：sklearn / jieba / pandas 懒加载，Flask 秒启不再误判卡死；必要时预导入关键链路并打印进度提示
> - **Debug 机制修复**：彻底放弃 `FLASK_DEBUG` 环境变量，改为根目录显式 **`.debug` 文件开关**，彻底根治环境变量残留导致 reloader 伪装退出、端口被抢占等诡异问题

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
├── templates/                # HTML 模板 (7 个页面, ECharts 可视化)
│   ├── base.html, input.html, data.html
│   ├── h.html (薪资柱状+学历饼图+经验饼图+城市横向柱状)
│   ├── ml.html (规则vs聚类对比图+城市分布图)
│   ├── advice.html, collect.html
│
├── tests/                    # 测试 (97 个用例, 全部通过)
│   ├── test_app_routes.py       — 路由与安全回归测试 (10 个用例: CSRF / 页码校验 / 采集口令 / 限流)
│   ├── test_agent_loop.py       — Agent 逻辑集成测试骨架 (预留, 待补齐真实用例)
│   ├── test_python_job_scraper.py — 采集参数构建单元测试 (27 个用例: 关键词 / 城市 / 页码 / 时间戳)
│   ├── test_salary_parser.py    — 薪资解析全覆盖测试 (20 个用例: 面议/万/千/年/日/·薪/奖金剥离)
│   ├── test_analysis_functions.py — classify/extract_city/tokenize/_fuzzy_match (32 个用例)
│   └── test_model_logic.py      — 聚类/预测模型核心逻辑测试 (8 个用例, mock DB)
│
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker 一键部署
├── .dockerignore             # Docker 忽略文件
│
├── cache/                    # 模型持久化 (joblib 二进制,切勿手动编辑)
├── logs/                     # 运行时日志 (gitignore, 5MB 旋转 × 3 备份)
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

# 2. 配置环境变量（.env，仅 Agent / 加固配置需要）
# 复制 .env.example 为 .env，按需填入:
#   DEEPSEEK_API_KEY=你的Key         (仅 Agent 问答页面需要)
#   FLASK_SECRET=64字符随机字符串    (用于 session 和 CSRF token 签名持久化；不填每次启动随机)
#   COLLECT_TOKEN=采集口令          (设置后采集接口要求校验口令，防误操作清空数据；不填不启用)
#   FLASK_HOST=127.0.0.1 / 0.0.0.0  (默认 127.0.0.1；0.0.0.0 才对外监听局域网)
#
#    ※ Debug 开关不再使用环境变量，改为文件开关：
#    ※ 想要启用 debug + reloader（模板热更新）时，在项目根目录 touch 一个空的 .debug 文件即可
#    ※ 日常开发建议保持关闭，否则 reloader 会 fork 子进程导致 print 丢失、端口残留、假退出
#    ※ .debug 文件已被 .gitignore 忽略

# 3. 启动 Web 服务
python app.py
# 终端会自动打印 本地访问(http://127.0.0.1:5000) + 同局域网访问地址

# 4. 命令行独立运行各模块验证
python -c "from analysis.xinzi import salary_distribution; print(salary_distribution())"
python -c "from analysis.jobtitle import classify_batch; print(classify_batch())"
python -c "from modeling.job_clustering import run_clustering; print(run_clustering())"
python -c "from modeling.salary_predict import train_and_evaluate; print(train_and_evaluate())"
python -c "from data.fix_duplicate_address import fix_addresses; print(fix_addresses())"
python -m pytest tests/ -v   # 运行全部测试 (97 个用例, 全部通过)
```

### 方式二：Docker 部署（推荐用于服务器/长期运行）

> **架构分工**：数据采集（Playwright + Chromium）依赖真实浏览器指纹对抗 WAF，因此在宿主机本地执行后写入 `data.db`；Docker 容器仅负责 Web 展示 + 模型推理 + Agent，通过 volume 挂载共享同一个 SQLite 数据库。镜像体积约 300MB（不含 Chromium）。

```bash
# 1. 先在本地采集一次数据 (Playwright 需要真实浏览器指纹)
python -c "from data.python_job_scraper import scrape_jobs; scrape_jobs()"

# 2. 启动 Docker 容器 (纯 Web 服务，不含爬虫)
# 方式一: docker-compose (推荐，最简单)
# 注：docker-compose.yml 已挂载 templates/、app.py、config.py 到容器 → 开发期改源码不用重建镜像
# 仅 data.db 持久化数据，模板改动容器立即生效
docker-compose up -d
# 访问 http://localhost:5000

# 方式二: 手动构建与运行
docker build -t job-analysis .
docker run -d -p 5000:5000 \
  -v $(pwd)/data.db:/app/data.db \
  -v $(pwd)/templates:/app/templates:ro \
  -v $(pwd)/app.py:/app/app.py:ro \
  -v $(pwd)/config.py:/app/config.py:ro \
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

## 更新日志（Changelog）

- **2026-07-01 · docs/config 同步：README 对齐项目现状 + docker-compose 热更新挂载 + .gitignore**
  - 测试用例总数从 README 声称的 70/37 → 实测 **97 passed**（test_analysis_functions 25→32，test_app_routes 14→10，补齐 test_salary_parser 的奖金剥离说明）；test_agent_loop 标注为「预留骨架，待补齐」
  - `.gitignore` 新增 `.qoder/`（Trae 本地知识库缓存）
  - `docker-compose.yml` 新增 templates / app.py / config.py 本地挂载：**开发期改模板和代码不再需要重建镜像**
  - 安全加固列表中新增「COLLECT_TOKEN 采集口令保护」到快速开始的环境变量说明中
  - README 安全/工程质量描述、快速开始 debug 说明、Docker 部署说明与 `app.py` / `.gitignore` / `docker-compose.yml` 代码完全对齐

- **2026-07-01 · fix: 饼图修复 + 启动性能与 Debug 机制全面整改（7 轮迭代）**
  - 学历/经验占比图从「环形图」回归真实配置：**实心饼状图** `radius: ['0%', '70%']`（注意：修改模板后若页面不生效，先检查 5000 端口是否残留 IDE 启动的旧 Flask 进程或 Docker `job-analysis` 容器）
  - **Debug 开关彻底改为 `.debug` 文件控制**：不再读取 `FLASK_DEBUG` 环境变量，根治环境变量残留导致的 reloader 伪装退出、端口抢占、print 丢失、假启动成功实际 502 等诡异问题
  - `use_reloader=debug`：只有显式放了 `.debug` 文件才开启 Werkzeug 子进程重载，日常关闭避免 fork
  - **启动性能优化多轮**：sklearn / jieba / pandas 先改为「懒加载」实现 Flask 秒启；后根据 VSCode 冷启动卡死的真实反馈，迭代为「选择性预导入关键链路 + 多段进度打印」，两者兼得
  - 终端启动时自动打印本地访问地址 `http://127.0.0.1:5000` 与同局域网访问地址（UDP 探测取 LAN IP）

- **2026-07-01 · feat: 测试覆盖 + ECharts 可视化**
  - 新增 3 个测试文件：`test_salary_parser.py`(20), `test_analysis_functions.py`(25), `test_model_logic.py`(8)
  - 测试总用例从 51 增至 70，覆盖薪资解析 / 职位分类 / 分词 / 聚类选 k / 模糊匹配
  - `/chart` 页面全面升级 ECharts（替代 Highcharts）：柱状图+饼图+城市横向柱状图
  - `/ml` 页面新增规则 vs KMeans 聚类对比图和城市分布图
  - `/chart` 路由新增 `city_data` 传参，城市分布可视图表化

- **2026-07-01 · feat: 工程质量提升 — 连接管理 + 模型持久化 + 日志系统**
  - Flask `g` + `teardown_appcontext` 管理 SQLite 连接，消除每个路由手动 open/close
  - joblib 持久化聚类和薪资预测模型到 `cache/`，重启免重训
  - `print` 全面替换为 `logging` + `RotatingFileHandler`，输出到 `logs/app.log`
  - 依赖清单新增 `joblib>=1.2`；`.gitignore` 新增 `logs/`

- **2026-07-01 · fix: add CSRF protection & harden app.run defaults**
  - 集成 Flask-WTF CSRFProtect；3 处 POST 表单加入 `csrf_token`
  - 新增 `app.secret_key`，通过 `FLASK_SECRET` 环境变量持久化
  - `debug/host` 改为环境变量驱动；默认关 debug、默认监听 `127.0.0.1`
  - 新增 `tests/test_app_routes.py`（10 个安全回归用例）
  - 依赖清单新增 `Flask-WTF>=1.0`
