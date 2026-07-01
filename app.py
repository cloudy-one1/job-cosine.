"""
完整Flask主程序 —— 替代教材 app.py。

跟教材的主要区别:
1. 数据库换成SQLite,不再需要Flask-SQLAlchemy这层ORM,
   直接用sqlite3做查询,跟项目里其他模块(region.py/jobtitle.py等)风格一致
2. 首页不再触发"实时爬虫",数据采集(collect_data.py)和网站展示是分离的两步
   ——这本身也是更合理的架构:数据采集可以独立、定期运行,
   网站只负责读取已采集好的数据并展示,不需要每次访问都现场爬一次
3. 新增 /advice 路由,接入Agent模块

项目包结构:
  data/       — 数据采集与清洗 (scraper, parser, cleaner)
  analysis/   — 描述性统计 (薪资、学历、经验、地区、职位分类)
  modeling/   — 机器学习模型 (聚类、薪资预测)
  agent/      — ReAct Agent 系统 (工具注册、推理循环)
  templates/  — Flask 模板

运行: python app.py
访问: http://127.0.0.1:5000
"""
import os
import sqlite3
import re as _re

from flask import Flask, render_template, request, redirect
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config

# --- 数据层 ---
from data.python_job_scraper import scrape_jobs
from data.salary_parser import parse_salary

# --- 描述性统计层 ---
import analysis.xinzi as xinzi
import analysis.xueli as xueli
import analysis.jinyan as jinyan
import analysis.region as region
import analysis.jobtitle as jobtitle

# --- 建模层 ---
import modeling.job_clustering as job_clustering
import modeling.salary_predict as salary_predict
from modeling.cache import update as _model_update, get as _model_get

# --- Agent 层 ---
from agent.agent_core import run_agent

app = Flask(__name__)

# --- 安全基础配置 ------------------------------------------------------------
# secret_key 用于 Flask session 签名与 Flask-WTF CSRF token 校验。
# 生产环境必须通过 FLASK_SECRET 环境变量注入固定值(否则重启后所有 session/token 失效)。
app.secret_key = os.environ.get('FLASK_SECRET') or os.urandom(32)

# 启用 Flask-WTF CSRF 保护。所有 POST 表单必须带 {{ csrf_token() }} 隐藏字段,
# 否则返回 400 Bad Request (防止跨站请求伪造)。
csrf = CSRFProtect(app)

# Flask-Limiter 速率限制: 全局限流 + 对危险路由(/collect)单独收紧
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)

# SQLite WAL 模式: 设一次即持久化到数据库文件,后续所有连接自动受益(并发读不阻塞写)
try:
    if os.path.exists(config.DB_PATH):
        _wal_conn = sqlite3.connect(config.DB_PATH)
        _wal_conn.execute("PRAGMA journal_mode=WAL")
        _wal_conn.close()
except Exception:
    pass

PER_PAGE = 12

# 聚类计算(jieba分词+TFIDF+KMeans选k)耗时几秒,在app启动时算一次缓存住,
# 不要让每次访问页面都重新跑一遍,否则用户体验很差。
# 薪资预测模型同理,训练好的模型保留在内存里复用。

def _has_data():
    """检查数据库中是否有可用的招聘数据。"""
    try:
        db = sqlite3.connect(config.DB_PATH)
        count = db.cursor().execute("SELECT COUNT(*) FROM data").fetchone()[0]
        db.close()
        return count > 0
    except Exception as e:
        print(f'[警告] 数据库读取失败: {e}')
        return False

print('正在预计算职位聚类和薪资预测模型(只在启动时跑一次)...')
if not _has_data():
    print('[警告] 数据库为空,跳过模型预计算。请先执行数据采集后再使用 /ml 和 Agent 功能。')
    _clustering_result = None
else:
    try:
        _clustering_result = job_clustering.run_clustering()
        _model_update(salary_predict.train_and_evaluate())   # 注入 modeling.cache,agent 自动共享
        print('预计算完成。')
    except Exception as e:
        print(f'[警告] 模型预计算失败: {e}。部分功能可能不可用。')
        _clustering_result = None


@app.route('/')
def index():
    return render_template('input.html')


@app.route('/list')
def list_data():
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    page = max(1, page)  # 避免页码为0或负数
    kw = request.args.get('kw', '').strip()
    city_raw = request.args.get('city', '').strip()
    cities = [c.strip() for c in _re.split(r'[,，\s]+', city_raw) if c.strip()]

    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()

    conditions = []
    params = []
    if kw:
        conditions.append("post LIKE ?")
        params.append(f'%{kw}%')
    if cities:
        city_conditions = " OR ".join(["address LIKE ?"] * len(cities))
        conditions.append(f"({city_conditions})")
        params.extend([f'%{c}%' for c in cities])
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    cursor.execute(
        f"SELECT post, company, address, salary_min, salary_max, dateT FROM data "
        f"{where_clause} LIMIT ? OFFSET ?",
        (*params, PER_PAGE, (page - 1) * PER_PAGE)
    )
    rows = cursor.fetchall()
    cursor.execute(f"SELECT COUNT(*) FROM data {where_clause}", params)
    total = cursor.fetchone()[0]

    db.close()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    return render_template(
        'data.html', rows=rows, kw=kw, city=city_raw, page=page,
        total=total, total_pages=total_pages
    )


@app.route('/chart')
def chart():
    xz = xinzi.xinzi()
    xl = xueli.xuelifun()
    jy = jinyan.jinyanfun()
    return render_template('h.html', xz=xz, xl=xl, jy=jy)


def _safe_model_metrics(mc):
    """当模型未训练时,返回安全的默认指标值,避免模板渲染崩溃。
    模板里使用 model_r2 / model_old_r2 / model_mae / baseline_mae 这4个键。"""
    defaults = {'model_r2': 0, 'model_old_r2': 0, 'model_mae': 0, 'baseline_mae': 0}
    if mc is None:
        return defaults
    return {
        'model_r2': mc.get('r2', 0),
        'model_old_r2': mc.get('old_r2', 0),
        'model_mae': mc.get('mae', 0),
        'baseline_mae': mc.get('baseline_mae', 0),
    }


@app.route('/ml')
def ml_page():
    mc = _model_get()
    metrics = _safe_model_metrics(mc)
    return render_template(
        'ml.html',
        clustering=_clustering_result,
        rule_based=jobtitle.jobtitlefun(),
        region_data=region.regionfun(),
        model_ready=mc is not None,
        **metrics
    )


@app.route('/predict', methods=['POST'])
def predict():
    city = request.form.get('city', '').strip()
    category = request.form.get('category', '').strip()
    edu = request.form.get('edu', '').strip() or '不限'
    exper = request.form.get('exper', '').strip() or '经验不限'

    predict_error = None
    predict_result = None

    mc = _model_get()
    if mc is None:
        predict_error = '薪资预测模型尚未训练,请先采集数据。'
    elif not city or not category:
        predict_error = '请输入城市和职位类别'
    else:
        pred, matched_edu, matched_exper, warns = salary_predict.predict_salary_safe(
            mc['model'], city, category, edu, exper,
            mc['valid_edu'], mc['valid_exper'],
            mc.get('valid_city'), mc.get('valid_category'),
        )
        predict_result = {
            'city': city, 'category': category,
            'edu': matched_edu, 'exper': matched_exper, 'pred': pred,
            'warnings': warns,
        }

    mc = _model_get()
    metrics = _safe_model_metrics(mc)
    return render_template(
        'ml.html',
        clustering=_clustering_result,
        rule_based=jobtitle.jobtitlefun(),
        region_data=region.regionfun(),
        model_ready=mc is not None,
        **metrics,
        predict_error=predict_error,
        predict_result=predict_result,
    )


@app.route('/collect', methods=['GET', 'POST'])
@limiter.limit("5 per hour")  # 采集接口单独限流,防止滥用
def collect():
    """
    用户指定关键词+城市,触发一次真实的51job实时采集(Playwright+stealth),
    采集结果写入data表,供后续所有分析(图表/聚类/预测/Agent)直接使用。

    表单本身在首页(input.html),这里只处理提交;GET请求(比如直接访问
    这个URL)重定向回首页,避免出现两份重复的输入框。

    注意: 这是同步阻塞调用,一次采集通常耗时5~10秒(过WAF)+每页约0.3秒,
    城市和页数设了上限,避免单次请求耗时过长。
    """
    if request.method != 'POST':
        return redirect('/')

    # --- 采集口令校验 --------------------------------------------------------
    # 若 .env 中设置了 COLLECT_TOKEN,则要求表单中提交匹配的 token 字段,
    # 否则拒绝采集 —— 防止演示/教学场景下被人误操作清空数据。
    if config.COLLECT_TOKEN:
        form_token = request.form.get('token', '')
        if form_token != config.COLLECT_TOKEN:
            return render_template(
                'collect.html',
                error='采集口令不正确,请联系管理员获取',
                keyword=request.form.get('kw', '').strip(),
                city=request.form.get('city', '').strip(),
            ), 403

    keyword = request.form.get('kw', '').strip()
    city_raw = request.form.get('city', '').strip()
    # 同时支持中文逗号"，"、英文逗号","、空格分隔,
    # 之前只认英文逗号,用户用中文输入法打的全角逗号"，"不会被拆开,
    # 导致整段文字被当成一个城市名传进去(实测踩到的真实bug)
    cities = [c.strip() for c in _re.split(r'[,，\s]+', city_raw) if c.strip()]
    try:
        pages = int(request.form.get('pages', 2))
    except ValueError:
        pages = 2
    pages = max(1, min(pages, 5))  # 安全上限,防止单次请求耗时过长

    if not keyword:
        return render_template('collect.html', error='请输入采集关键词')

    try:
        jobs = scrape_jobs(keyword, cities, pages_per_city=pages)
    except Exception as e:
        # 不把原始异常信息直接抛给前端,避免泄露内部路径/堆栈信息
        return render_template('collect.html', error='采集过程发生错误,请稍后重试',
                                keyword=keyword, city=city_raw)

    if not jobs:
        return render_template(
            'collect.html',
            error='没有采集到任何数据,可能是WAF拦截了这次请求,或者关键词/城市没有匹配结果,换个关键词或稍后再试',
            keyword=keyword, city=city_raw,
        )

    # 先写入临时数据,确认成功后再替换旧数据(原子性保护:
    # 如果写入过程中途失败,旧数据依然保留,不会出现空库)
    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()
    success = 0
    for j in jobs:
        smin, smax = parse_salary(j['salary_raw'])
        try:
            cursor.execute(
                "insert into data (post,company,address,salary_min,salary_max,"
                "dateT,edu,exper,content) values(?,?,?,?,?,?,?,?,?)",
                (j['post'], j['company'], j['address'], smin, smax,
                 j['dateT'], j['edu'], j['exper'], '')
            )
            success += 1
        except Exception:
            pass
    # 只有成功写入至少一条数据后,才清空旧数据并提交
    if success > 0:
        cursor.execute(
            "DELETE FROM data WHERE rowid NOT IN "
            "(SELECT rowid FROM data ORDER BY rowid DESC LIMIT ?)",
            (success,)
        )
    db.commit()
    db.close()

    # 数据变了,聚类和薪资预测模型(在app启动时算过一次缓存住)
    # 也要跟着重新算一遍,否则 /chart 和 /ml 页面会显示基于旧数据的结果
    global _clustering_result
    try:
        _clustering_result = job_clustering.run_clustering()
        _model_update(salary_predict.train_and_evaluate())  # 同步更新建模缓存
    except Exception as e:
        print(f'[警告] 采集后模型重算失败: {e}')

    return render_template(
        'collect.html', success_count=success, total_count=len(jobs),
        keyword=keyword, city=city_raw,
    )


@app.route('/advice', methods=['GET', 'POST'])
def advice():
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if not question:
            return render_template('advice.html', error='请输入你的问题')
        api_key = getattr(config, 'DEEPSEEK_API_KEY', '')
        if not api_key:
            return render_template('advice.html', error='请先在config.py里设置DEEPSEEK_API_KEY', question=question)
        try:
            answer, trace = run_agent(question, api_key, max_steps=5, verbose=False)
        except Exception as e:
            return render_template('advice.html', error='Agent调用失败,请稍后重试', question=question)
        return render_template('advice.html', question=question, answer=answer, trace=trace)
    return render_template('advice.html')


# --- 模板全局变量注入 ------------------------------------------------------------
@app.context_processor
def inject_globals():
    """向所有模板注入全局变量,避免每个路由手动传参。"""
    return {'collect_token_required': bool(config.COLLECT_TOKEN)}


if __name__ == '__main__':
    # --- 生产安全默认值: debug 关、监听 127.0.0.1 --------------------------------
    # 需要开启 debug 或对外监听时,通过环境变量显式开启,避免误部署到公网:
    #   set FLASK_DEBUG=1        (Windows cmd)
    #   $env:FLASK_DEBUG="1"     (PowerShell)
    #   export FLASK_DEBUG=1     (Linux/macOS)
    #   FLASK_HOST=0.0.0.0       (显式开启对外访问,局域网其他设备才能访问)
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    host = os.environ.get('FLASK_HOST', '127.0.0.1')

    # threaded=True: 允许并发处理请求,避免/collect 阻塞其他页面浏览
    # use_reloader=False: 关闭文件变化自动重启,防止中断正在进行的实时采集
    app.run(debug=debug, host=host, threaded=True, use_reloader=False)
