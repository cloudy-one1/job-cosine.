"""
51job 实时数据采集模块。

使用 Playwright(无头 Chromium + stealth 补丁)绕过 WAF,
然后在已通过认证的浏览器会话内发起 API 调用,获取分页职位列表。
需要安装 playwright、playwright-stealth 以及 Chromium 浏览器。

独立使用(写入 data.db):
    python python_job_scraper.py

作为库使用(返回字典列表):
    from python_job_scraper import scrape_jobs
    jobs = scrape_jobs(keyword='java', cities=['杭州', '成都'], pages_per_city=2)
"""
import time
import random
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# 51job 城市映射表:中文城市名 -> API 需要的数字编码
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

# 在已认证的浏览器页面内执行的 JavaScript:发起 JSON 搜索接口。
# 成功返回普通 dict,WAF/网络失败返回 {error: ...} 标记。
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
        if (text.startsWith('<') || text.length < 100) return {error: 'WAF blocked'};
        return JSON.parse(text);
    } catch(e) {
        return {error: e.message};
    }
}
"""


def resolve_city_code(city_name):
    """根据中文城市名返回 51job 的城市编码,未知则返回 None。

    进行大小写不敏感匹配,也接受部分匹配(如 \"广东\" 或去掉 \"市\" 后缀)。
    对长度进行限制,避免被错误拆分的长字符串误匹配到不相关条目。
    """
    city_name = city_name.strip()
    if city_name in CITY_CODES:
        return CITY_CODES[city_name]
    if len(city_name) <= 6:
        for name, code in CITY_CODES.items():
            if name in city_name or city_name in name:
                return code
    return None


def build_api_params(keyword, job_area, page_num):
    """构建 51job 搜索页单条 API 调用的查询字符串参数。"""
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
    """对每个传入的城市抓取 pages_per_city 页的职位列表。

    返回字典列表,字段为: post, company, address, salary_raw,
    edu, exper, dateT, scrape_date。按 job id 去重。

    若调用方未传入任何可解析城市,默认回退到北京。
    """
    valid_cities = []
    for c in cities:
        code = resolve_city_code(c)
        if code:
            valid_cities.append((c, code))

    if not valid_cities:
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

        # 轮询等待页面渲染出职位列表,表示 WAF 挑战已通过、Cookie 生效
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
    demo_keyword = input('请输入采集关键词(默认 python): ').strip() or 'python'
    demo_cities_input = input('请输入城市(多个以逗号分隔,默认 北京 上海 广州 深圳): ').strip()
    if demo_cities_input:
        demo_cities = [c.strip() for c in demo_cities_input.split(',') if c.strip()]
    else:
        demo_cities = ['北京', '上海', '广州', '深圳']
    demo_pages = int(input('每个城市抓取页数(默认 3): ').strip() or '3')

    print(f'开始采集:关键词={demo_keyword}, 城市={demo_cities}, 每城{demo_pages}页')
    jobs = scrape_jobs(demo_keyword, demo_cities, pages_per_city=demo_pages)
    print(f'采集完成,共 {len(jobs)} 条职位')

    import csv
    import config
    import sqlite3
    from import_fresh_data import parse_salary

    csv_path = 'fresh_job_data.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(
            f, fieldnames=['post', 'company', 'address', 'salary_raw',
                           'edu', 'exper', 'dateT', 'scrape_date']
        )
        writer.writeheader()
        for job in jobs:
            writer.writerow(job)
    print(f'已写入 {csv_path}')

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
    print(f'已写入 data.db: {success} / {len(jobs)} 条')
