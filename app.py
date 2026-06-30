"""
招聘数据分析项目的 Flask 主程序。

路由表:
  GET  /           -> 首页(输入关键词和城市表单)
  GET  /list       -> 分页职位列表,支持按关键词和城市过滤
  GET  /chart      -> 薪资 / 学历 / 经验分布图表页
  GET  /ml         -> 聚类 + 规则分类 + 薪资预测展示页
  POST /predict    -> 根据城市和职位类别预测薪资
  GET|POST /collect-> 触发一次实时数据采集
  GET|POST /advice -> 与基于大模型的求职助手对话
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
from import_fresh_data import parse_salary
from agent_core import run_agent

app = Flask(__name__)

PER_PAGE = 12

# 启动时预计算代价较大的两个模块(聚类 jieba + TF-IDF + KMeans 轮询 约数秒;
# 线性回归也有开销)。结果缓存在进程内,以便页面加载速度保持稳定。
print('正在预计算聚类结果与薪资预测模型...')
_clustering_result = job_clustering.run_clustering()
_salary_model_result = salary_predict.train_and_evaluate()
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
    """使用 Playwright + stealth 绕过 WAF,实时采集 51job 职位。

    采集结果写入 data 表,并刷新进程内的聚类和薪资预测缓存,
    以便统计页能立刻反映新数据。注意:该路由是阻塞式的,可能较慢。
    """
    if request.method != 'POST':
        return redirect('/')

    keyword = request.form.get('kw', '').strip()
    city_raw = request.form.get('city', '').strip()
    # 同时接受中英文逗号、空白分隔的多个城市,避免中文输入法下输入的纯中文逗号
    # 被整合成一个"城市"字符串导致下游匹配失败。
    cities = [c.strip() for c in _re.split(r'[,，\s]+', city_raw) if c.strip()]
    try:
        pages = int(request.form.get('pages', 2))
    except ValueError:
        pages = 2
    pages = max(1, min(pages, 5))

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
            error='没有采集到任何数据,可能是WAF拦截了这次请求,换个关键词或稍后再试',
            keyword=keyword, city=city_raw,
        )

    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()
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

    # 数据更新后,重新计算聚类与预测模型,确保后续页面展示新数据
    global _clustering_result, _salary_model_result
    _clustering_result = job_clustering.run_clustering()
    _salary_model_result = salary_predict.train_and_evaluate()

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
            return render_template('advice.html', error='请先设置DEEPSEEK_API_KEY', question=question)
        try:
            answer, trace = run_agent(question, api_key, max_steps=5, verbose=False)
        except Exception as e:
            return render_template('advice.html', error=f'Agent调用出错: {e}', question=question)
        return render_template('advice.html', question=question, answer=answer, trace=trace)
    return render_template('advice.html')


if __name__ == '__main__':
    # 使用 threaded=True 支持并发请求,避免采集长时间运行时卡住其他统计页
    app.run(debug=True, host='0.0.0.0', threaded=True)
