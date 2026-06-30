"""
完整Flask主程序 —— 替代教材 app.py。

跟教材的主要区别:
1. 数据库换成SQLite,不再需要Flask-SQLAlchemy这层ORM,
   直接用sqlite3做查询,跟项目里其他模块(region.py/jobtitle.py等)风格一致
2. 首页不再触发"实时爬虫",数据采集(collect_data.py)和网站展示是分离的两步
   ——这本身也是更合理的架构:数据采集可以独立、定期运行,
   网站只负责读取已采集好的数据并展示,不需要每次访问都现场爬一次
3. 新增 /advice 路由,接入Agent模块

运行: python app.py
访问: http://127.0.0.1:5000
"""
import sqlite3
import re as _re

from flask import Flask, render_template, request, redirect

import config
import xinzi
import xueli
import jinyan
import region
import jobtitle
import job_clustering
import salary_predict
import python_job_scraper
from salary_parser import parse_salary
from agent_core import run_agent
from agent_tools import set_model_result

app = Flask(__name__)

PER_PAGE = 12

# 聚类计算(jieba分词+TFIDF+KMeans选k)耗时几秒,在app启动时算一次缓存住,
# 不要让每次访问页面都重新跑一遍,否则用户体验很差。
# 薪资预测模型同理,训练好的模型保留在内存里复用。
print('正在预计算职位聚类和薪资预测模型(只在启动时跑一次)...')
_clustering_result = job_clustering.run_clustering()
_salary_model_result = salary_predict.train_and_evaluate()
set_model_result(_salary_model_result)   # 同步注入给 agent_tools,避免重复训练
print('预计算完成。')


@app.route('/')
def index():
    return render_template('input.html')


@app.route('/list')
def list_data():
    page = int(request.args.get('page', 1))
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


@app.route('/ml')
def ml_page():
    return render_template(
        'ml.html',
        clustering=_clustering_result,
        rule_based=jobtitle.jobtitlefun(),
        region_data=region.regionfun(),
        model_r2=_salary_model_result['r2'],
        model_old_r2=_salary_model_result['old_r2'],
        model_mae=_salary_model_result['mae'],
        baseline_mae=_salary_model_result['baseline_mae'],
    )


@app.route('/predict', methods=['POST'])
def predict():
    city = request.form.get('city', '').strip()
    category = request.form.get('category', '').strip()
    edu = request.form.get('edu', '').strip() or '不限'
    exper = request.form.get('exper', '').strip() or '经验不限'

    predict_error = None
    predict_result = None
    if not city or not category:
        predict_error = '请输入城市和职位类别'
    else:
        pred, matched_edu, matched_exper, warns = salary_predict.predict_salary_safe(
            _salary_model_result['model'], city, category, edu, exper,
            _salary_model_result['valid_edu'], _salary_model_result['valid_exper'],
        )
        predict_result = {
            'city': city, 'category': category,
            'edu': matched_edu, 'exper': matched_exper, 'pred': pred,
            'warnings': warns,
        }

    return render_template(
        'ml.html',
        clustering=_clustering_result,
        rule_based=jobtitle.jobtitlefun(),
        region_data=region.regionfun(),
        model_r2=_salary_model_result['r2'],
        model_old_r2=_salary_model_result['old_r2'],
        model_mae=_salary_model_result['mae'],
        baseline_mae=_salary_model_result['baseline_mae'],
        predict_error=predict_error,
        predict_result=predict_result,
    )


@app.route('/collect', methods=['GET', 'POST'])
def collect():
    """
    用户指定关键词+城市,触发一次真实的51job实时采集(Playwright+stealth),
    采集结果写入data表,供后续所有分析(图表/聚类/预测/Agent)直接使用。

    表单本身在首页(input.html),这里只处理提交;GET请求(比如直接访问
    这个URL)重定向回首页,避免出现两份重复的输入框。

    注意: 这是同步阻塞调用,一次采集通常耗时10秒(过WAF)+每页约1秒,
    城市和页数设了上限,避免单次请求耗时过长。
    """
    if request.method != 'POST':
        return redirect('/')

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
        jobs = python_job_scraper.scrape_jobs(keyword, cities, pages_per_city=pages)
    except Exception as e:
        return render_template('collect.html', error=f'采集出错: {e}',
                                keyword=keyword, city=city_raw)

    if not jobs:
        return render_template(
            'collect.html',
            error='没有采集到任何数据,可能是WAF拦截了这次请求,或者关键词/城市没有匹配结果,换个关键词或稍后再试',
            keyword=keyword, city=city_raw,
        )

    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()
    # 每次实时采集都是一次新的分析案例,清空上一次的结果,
    # 跟教材4.4.6节 data_clr() 的设计思路一致
    cursor.execute("DELETE FROM data")
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
    db.commit()
    db.close()

    # 数据变了,聚类和薪资预测模型(在app启动时算过一次缓存住)
    # 也要跟着重新算一遍,否则 /chart 和 /ml 页面会显示基于旧数据的结果
    global _clustering_result, _salary_model_result
    _clustering_result = job_clustering.run_clustering()
    _salary_model_result = salary_predict.train_and_evaluate()
    set_model_result(_salary_model_result)   # agent 模型同步更新

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
            return render_template('advice.html', error=f'Agent调用出错: {e}', question=question)
        return render_template('advice.html', question=question, answer=answer, trace=trace)
    return render_template('advice.html')


if __name__ == '__main__':
    # host='0.0.0.0': 监听所有网络接口,同一局域网内的其他设备可以通过你的局域网IP访问
    # (默认只监听127.0.0.1,只有本机能访问)
    # threaded=True: 允许同时处理多个请求,避免/collect这种耗时较长的实时采集
    # 阻塞了其他人正常浏览页面
    # debug=True: 保留调试模式,出错时会显示详细的堆栈信息(方便排查问题)
    # use_reloader=False: 关闭文件变化自动重启,防止IDE保存文件导致正在
    # 进行的实时采集被中断(采集过程中Flask重启会让浏览器出现ERR_CONNECTION_RESET)
    # 注意: 之前批量修改了十几个文件的注释,导致所有文件的修改时间都是"刚刚",
    # Flask 的 watchdog 会误以为文件持续在变化而反复重启,这是为什么之前没问题、
    # 改了注释后才出现问题的根因
    app.run(debug=True, host='0.0.0.0', threaded=True, use_reloader=False)
