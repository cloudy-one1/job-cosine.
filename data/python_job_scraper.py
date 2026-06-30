"""
51job 实时采集模块(可参数化版本)。

跟最早那版的区别: 之前关键词("python")和城市(北京/上海/广州/深圳)是写死的常量,
这一版改成函数参数,Flask那边可以接收用户在网页上填的关键词+城市,直接调用
scrape_jobs() 拿到结果,不需要再改代码。

技术思路参考: https://github.com/gitychzh/jobSpider (无LICENSE声明,
本文件未直接复制该仓库代码,而是参考其"Playwright过WAF + 浏览器内fetch调用
真实API"的思路自行重写)。

依赖安装: pip install playwright playwright-stealth
         playwright install chromium

用法(命令行直接跑,效果跟网页上的"实时采集"完全一致——直接写入data.db):
    python data/python_job_scraper.py

用法(被其他代码调用,比如Flask路由):
    from data.python_job_scraper import scrape_jobs
    jobs = scrape_jobs(keyword='java', cities=['杭州', '成都'], pages_per_city=2)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import random
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# 51job城市代码表(来自51job官方城市代码表,覆盖国内30个主要城市)
CITY_CODES = {
    "北京": "010000", "天津": "050000", "大连": "230300", "沈阳": "230200",
    "长春": "240200", "哈尔滨": "220200", "石家庄": "160200",
    "上海": "020000", "南京": "070200", "苏州": "070300", "杭州": "080200",
    "宁波": "080300", "合肥": "150200", "济南": "120200", "青岛": "120300",
    "福州": "110200", "厦门": "110300", "南昌": "130200", "无锡": "070400",
    "常州": "070500",
    "广州": "030200", "深圳": "040000", "东莞": "030800", "武汉": "180200",
    "长沙": "190200", "郑州": "170200",
    "西安": "200200", "成都": "090200", "重庆": "060000", "昆明": "250200",
}

JS_FETCH_API = """
async (params) => {
    const url = 'https://we.51job.com/api/job/search-pc?' + new URLSearchParams(params).toString();
    try {
        const res = await fetch(url, {
            method: 'GET',
            credentials: 'include',
            headers: {'Accept': 'application/json, text/plain, */*'}
        });
        if (!res.ok) return {error: 'HTTP ' + res.status};
        const text = await res.text();
        if (text.startsWith('<') || text.length < 100) return {error: 'WAF拦截'};
        return JSON.parse(text);
    } catch(e) {
        return {error: e.message};
    }
}
"""


def resolve_city_code(city_name):
    """把用户输入的城市名转成51job城市代码,找不到返回None"""
    city_name = city_name.strip()
    if city_name in CITY_CODES:
        return CITY_CODES[city_name]
    # 容错: 用户输入"广东"这种省份名,或者打错字带了"市"字,做一个宽松匹配。
    # 但只在输入长度合理(<=6个字符)时才做这个模糊匹配——
    # 真实城市/省份名不会很长,如果传进来的是一长串没拆开的文字
    # (比如逗号分隔符没识别导致多个城市名粘在一起),不应该被误判匹配上
    # 某个城市(这是实测踩到过的真实bug,城市拆分失败时曾经误判成功过)。
    if len(city_name) <= 6:
        for name, code in CITY_CODES.items():
            if name in city_name or city_name in name:
                return code
    return None


def build_api_params(keyword, job_area, page_num):
    return {
        'api_key': '51job',
        'timestamp': int(time.time() * 1000),
        'keyword': keyword,
        'searchType': '2',
        'jobArea': job_area,
        'issueDate': '4',
        'sortType': '0',
        'pageNum': page_num,
        'keywordType': '2',
        'pageSize': '20',
        'source': '1',
        'pageCode': 'sou|sou|soulb',
        'scene': '7',
    }


def scrape_jobs(keyword, cities, pages_per_city=3, progress_callback=None):
    """
    核心函数: 给定关键词 + 城市名列表,实时采集51job数据。

    参数:
        keyword: 搜索关键词,比如 'python' / 'java'
        cities: 城市名列表,比如 ['北京', '上海'];传 ['全国'] 或空列表时,
                默认用北京作为WAF验证的入口城市,但只采集这一个城市
                (大范围"全国"采集会很慢,不建议)
        pages_per_city: 每个城市采集几页,每页20条
        progress_callback: 可选,一个函数(city, page, count) -> None,
                用于在网页上实时显示采集进度(比如Flask里可以传一个打印日志的函数)

    返回: list of dict,字段跟项目数据库schema一致
          (post, company, address, salary_raw, edu, exper, dateT, scrape_date)

    注意: 这个函数会真的打开一个无头浏览器访问51job,耗时通常是
          "10秒左右过WAF" + "每页约1秒",城市越多、页数越多越慢。
          调用方(比如Flask路由)要注意这是同步阻塞调用,不要在每个普通请求里
          都触发,只应该作为一个用户主动点击的"实时采集"动作。
    """
    valid_cities = []
    for c in cities:
        code = resolve_city_code(c)
        if code:
            valid_cities.append((c, code))

    if not valid_cities:
        # 没有有效城市,默认用北京当入口
        valid_cities = [("北京", CITY_CODES["北京"])]

    all_jobs = []
    all_seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        Stealth().apply_stealth_sync(context)

        page = context.new_page()

        first_code = valid_cities[0][1]
        search_url = (
            f"https://we.51job.com/pc/search?keyword={keyword}&keywordType=2"
            f"&jobArea={first_code}&issuedDate=4&pageNum=1&pageSize=20"
        )
        page.goto(search_url, timeout=30000, wait_until='domcontentloaded')

        for _ in range(30):
            try:
                cnt = page.evaluate("document.querySelectorAll('.joblist-item').length")
                if cnt >= 1:
                    break
            except Exception:
                pass
            time.sleep(1)

        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        for city, code in valid_cities:
            for pg in range(1, pages_per_city + 1):
                params = build_api_params(keyword, code, pg)
                time.sleep(random.uniform(0.5, 1.5))
                data = page.evaluate(JS_FETCH_API, params)

                if isinstance(data, dict) and 'error' in data:
                    break

                job_list = data.get('resultbody', {}).get('job', {}).get('items', [])
                if not job_list:
                    break

                added = 0
                for j in job_list:
                    jid = str(j.get('jobId', ''))
                    title = (j.get('jobName') or '').strip()
                    if not jid or not title or jid in all_seen:
                        continue
                    all_seen.add(jid)

                    job_area = (j.get('jobAreaString') or '').strip()
                    if job_area.startswith(city):
                        address = job_area.replace('·', '-')
                    elif job_area:
                        address = city + '-' + job_area.replace('·', '-')
                    else:
                        address = city

                    all_jobs.append({
                        'post': title,
                        'company': (j.get('companyName') or '').strip(),
                        'address': address,
                        'salary_raw': (j.get('provideSalaryString') or '').strip(),
                        'edu': (j.get('degreeString') or '').strip(),
                        'exper': (j.get('workYearString') or '').strip(),
                        'dateT': (j.get('issueDateString') or '').strip(),
                        'scrape_date': now,
                    })
                    added += 1

                if progress_callback:
                    progress_callback(city, pg, added)
                if added == 0:
                    break

        page.close()
        browser.close()

    return all_jobs


if __name__ == '__main__':
    import sqlite3
    import config
    from data.salary_parser import parse_salary

    jobs = scrape_jobs(
        keyword='python',
        cities=['北京', '上海', '广州', '深圳'],
        pages_per_city=5,
        progress_callback=lambda city, pg, n: print(f'[{city}] 第{pg}页 +{n}条'),
    )
    print(f"\n共采集到 {len(jobs)} 条数据")

    if not jobs:
        print("没有采集到数据,可能是WAF拦截了这次请求")
    else:
        db = sqlite3.connect(config.DB_PATH)
        cursor = db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post TEXT, company TEXT, address TEXT,
                salary_min REAL, salary_max REAL,
                dateT TEXT, edu TEXT, exper TEXT, content TEXT
            )
        """)
        # 跟教材4.4.6节 data_clr() 的设计思路一致: 每次新采集前清空旧数据,
        # 也跟网页 /collect 路由的实际行为保持一致,避免同一份数据
        # 出现"命令行跑出来一套、网页跑出来另一套"的不一致情况
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
            except Exception as e:
                print('插入失败:', j, e)

        db.commit()
        db.close()
        print(f"已写入数据库: 成功 {success} 条 (保存在 {config.DB_PATH})")
