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
import sys
import warnings

# 消掉 jieba → pkg_resources 的弃用警告
warnings.filterwarnings('ignore', message='pkg_resources is deprecated', category=UserWarning)

import sqlite3
import re as _re
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request, redirect, g
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config

# --- 日志系统 ----------------------------------------------------------------
# 同时输出到旋转日志文件(每5MB切一个,保留3个备份)和控制台
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(_log_dir, exist_ok=True)

_logger = logging.getLogger('job_analysis')
_logger.setLevel(logging.INFO)

_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, 'app.log'), maxBytes=5 * 1024 * 1024, backupCount=3,
    encoding='utf-8'
)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
))
_logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
_logger.addHandler(_console_handler)

# --- 数据层 ---
from data.python_job_scraper import scrape_jobs
from data.salary_parser import parse_salary

# --- 模型缓存（仅此模块本身轻量，内部含延迟导入） ---
from modeling.cache import update as _model_update, get as _model_get

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


# --- 数据库连接管理 (Flask g 复用) -----------------------------------------
def get_db():
    """获取当前请求上下文中的 SQLite 连接;不存在则创建。
    连接在整个请求生命周期内复用,teardown 时自动关闭。"""
    if 'db' not in g:
        g.db = sqlite3.connect(config.DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """请求结束时关闭数据库连接,避免连接泄漏。"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _raw_connect():
    """为非请求上下文(启动预计算等)提供独立连接,调用方自行关闭。"""
    return sqlite3.connect(config.DB_PATH)


# --- 模型持久化 ------------------------------------------------------------
# 启动时优先从磁盘加载已训练的模型,避免每次重启都重训 (joblib)
def _load_or_train_models():
    """尝试加载磁盘缓存的模型;失败或不存在则重训并持久化。"""
    import joblib as _joblib
    import modeling.job_clustering as job_clustering
    import modeling.salary_predict as salary_predict

    _cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    os.makedirs(_cache_dir, exist_ok=True)
    _cluster_path = os.path.join(_cache_dir, 'clustering_result.joblib')
    _salary_path = os.path.join(_cache_dir, 'salary_model.joblib')

    if not _has_data():
        _logger.warning('数据库为空,跳过模型预计算。请先执行数据采集后再使用 /ml 和 Agent 功能。')
        return None

    # 尝试加载持久化模型
    cluster = None
    try:
        if os.path.exists(_cluster_path):
            cluster = _joblib.load(_cluster_path)
            _logger.info('从磁盘加载聚类结果')
    except Exception as e:
        _logger.warning('聚类结果加载失败,将重新计算: %s', e)

    try:
        if os.path.exists(_salary_path):
            salary_result = _joblib.load(_salary_path)
            _model_update(salary_result)
            _logger.info('从磁盘加载薪资预测模型 (R²=%.3f)', salary_result['r2'])
        else:
            salary_result = None
    except Exception as e:
        _logger.warning('薪资模型加载失败,将重新训练: %s', e)
        salary_result = None

    # 缺失则训练
    try:
        if cluster is None:
            cluster = job_clustering.run_clustering()
            _joblib.dump(cluster, _cluster_path)
            _logger.info('聚类模型已训练并保存到磁盘 (k=%d)', cluster['k'])
        if salary_result is None:
            salary_result = salary_predict.train_and_evaluate()
            _model_update(salary_result)
            _joblib.dump(salary_result, _salary_path)
            _logger.info('薪资预测模型已训练并保存到磁盘 (R²=%.3f)', salary_result['r2'])
    except Exception as e:
        _logger.error('模型训练失败: %s。部分功能可能不可用。', e)
        if cluster is None:
            cluster = None

    return cluster


def _has_data():
    """检查数据库中是否有可用的招聘数据。"""
    try:
        db = _raw_connect()
        count = db.cursor().execute("SELECT COUNT(*) FROM data").fetchone()[0]
        db.close()
        return count > 0
    except Exception as e:
        _logger.warning('数据库读取失败: %s', e)
        return False


# 聚类结果懒加载：不在启动时触发 sklearn/pandas 的首次 .pyc 编译，
# 等首个访问 /ml 或 /predict 的请求到来时才计算（避免误判启动卡死）
_clustering_cache = None

def _get_clustering():
    """获取聚类结果（首次调用时训练+缓存，后续直接返回）。"""
    global _clustering_cache
    if _clustering_cache is not None:
        return _clustering_cache
    _logger.info('正在预计算职位聚类和薪资预测模型(只在第一次访问时跑一次)...')
    _clustering_cache = _load_or_train_models()
    if _clustering_cache is not None:
        _logger.info('预计算完成。')
    return _clustering_cache


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

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        f"SELECT post, company, address, salary_min, salary_max, dateT FROM data "
        f"{where_clause} LIMIT ? OFFSET ?",
        (*params, PER_PAGE, (page - 1) * PER_PAGE)
    )
    rows = cursor.fetchall()
    cursor.execute(f"SELECT COUNT(*) FROM data {where_clause}", params)
    total = cursor.fetchone()[0]
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    return render_template(
        'data.html', rows=rows, kw=kw, city=city_raw, page=page,
        total=total, total_pages=total_pages
    )


@app.route('/chart')
def chart():
    import analysis.xinzi as xinzi
    import analysis.xueli as xueli
    import analysis.jinyan as jinyan
    import analysis.region as region
    xz = xinzi.xinzi()
    xl = xueli.xuelifun()
    jy = jinyan.jinyanfun()
    city_data = region.regionfun()
    return render_template('h.html', xz=xz, xl=xl, jy=jy, city_data=city_data)


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
    import analysis.jobtitle as jobtitle
    import analysis.region as region
    mc = _model_get()
    metrics = _safe_model_metrics(mc)
    return render_template(
        'ml.html',
        clustering=_get_clustering(),
        rule_based=jobtitle.jobtitlefun(),
        region_data=region.regionfun(),
        model_ready=mc is not None,
        **metrics
    )


@app.route('/predict', methods=['POST'])
def predict():
    import modeling.salary_predict as salary_predict
    import analysis.jobtitle as jobtitle
    import analysis.region as region

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
        clustering=_get_clustering(),
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
    db = get_db()
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

    # 数据变了,聚类和薪资预测模型(在app启动时算过一次缓存住)
    # 也要跟着重新算一遍,否则 /chart 和 /ml 页面会显示基于旧数据的结果
    global _clustering_cache
    import joblib as _joblib
    import modeling.job_clustering as job_clustering
    import modeling.salary_predict as salary_predict
    _cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    _cluster_path = os.path.join(_cache_dir, 'clustering_result.joblib')
    _salary_path = os.path.join(_cache_dir, 'salary_model.joblib')
    try:
        _clustering_cache = job_clustering.run_clustering()
        _joblib.dump(_clustering_cache, _cluster_path)
        salary_result = salary_predict.train_and_evaluate()
        _model_update(salary_result)
        _joblib.dump(salary_result, _salary_path)
        _logger.info('采集后模型已重新训练并持久化')
    except Exception as e:
        _logger.warning('采集后模型重算失败: %s', e)

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
            from agent.agent_core import run_agent
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
    # --- 启动配置 ---------------------------------------------------------------
    # debug 默认关闭，避免 Flask 强制开启 reloader（reloader fork 子进程后，
    # 父进程的 print 输出丢失，且子进程启动失败时伪装为"正常退出"→ERR_CONNECTION_REFUSED）。
    # 如需热更新: 在项目根目录 touch 一个 .debug 文件即可（不建议日常使用）。
    # 局域网访问: $env:FLASK_HOST="0.0.0.0"
    _debug_flag = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.debug')
    debug = os.path.exists(_debug_flag)
    if debug:
        print("[WARN] 检测到 .debug 文件，已启用 debug 模式（含 reloader）", flush=True)
    host = os.environ.get('FLASK_HOST', '127.0.0.1')

    # threaded=True: 允许并发处理请求,避免/collect 阻塞其他页面浏览
    port = 5000
    print(f"\n  -> 本地访问: http://127.0.0.1:{port}", flush=True)
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.254.254.254', 1))
        lan_ip = s.getsockname()[0]
        s.close()
        print(f"  -> 局域网访问: http://{lan_ip}:{port}    (同局域网设备可用)\n", flush=True)
    except Exception:
        print(flush=True)
    app.run(debug=debug, host=host, port=port, threaded=True, use_reloader=debug)
