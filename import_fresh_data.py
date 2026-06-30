"""
把 python_job_scraper.py 抓到的 fresh_job_data.csv(362条真实北上广深Python
岗位数据,采集于今天)解析后写入 data.db。

跟之前 import_job_dataset.py 的区别:
1. 数据是真实的、新鲜的(今天采集),不是2017年的快照
2. edu(学历)、exper(经验)这两个字段这次是真实值,不再是空字符串
   ——这意味着之前因为数据集限制而搁置的"学历分析""经验分析"
   (教材原版 xueli.py / jinyan.py 想做的事)现在可以做真的了

用法:
    python import_fresh_data.py
    (会清空data表,用这362条新数据重新填充;如果想保留老数据对比,
    告诉我,可以改成另存一张表)
"""
import re
import csv
import sqlite3
import config


def parse_salary(raw):
    """
    解析51job真实API返回的薪资字符串,返回(min, max),单位千元/月。
    常见格式: "1.5-2万/月" "8千-1.2万/月" "15-25万/年" "1.3-1.5万·13薪"
             "面议" "3千-4.5千/月" "1万以上/月"

    关键陷阱(实测踩到过,记录下来): 中文薪资简写里,单位经常只写在
    最后一个数字后面,比如"1.5-2万"实际表示"1.5万-2万",不是"1.5(不知道单位)-2万"。
    如果直接按"字符串里有没有'万'/'千'"整体判断,会把单位错误地套用到
    每一个数字上,导致"8千-1.2万"被错误解析成"80-12"(都按万算)。
    正确做法是:每个数字只认自己紧跟着的单位,缺单位的数字向后看,
    继承后面最近一个数字的单位。
    """
    if not raw or '面议' in raw:
        return 0.0, 0.0

    raw_clean = raw.split('·')[0]
    is_year = '/年' in raw_clean
    is_day = '/天' in raw_clean

    matches = [(num, unit) for num, unit in re.findall(r'(\d+\.?\d*)(万|千)?', raw_clean) if num]
    if not matches:
        return 0.0, 0.0

    if is_day:
        vmin = round(float(matches[0][0]) * 21.75 / 1000, 2)
        vmax = round(float(matches[-1][0]) * 21.75 / 1000, 2)
        return vmin, vmax

    # 缺单位的数字,向后继承最近一个数字的单位("1.5-2万" -> 1.5也按"万"算)
    filled = []
    last_unit = None
    for num, unit in reversed(matches):
        if unit:
            last_unit = unit
        filled.append((num, unit or last_unit))
    filled.reverse()

    def to_k(num_str, unit):
        v = float(num_str)
        return v * 10 if unit == '万' else v  # 千 或 无单位 都按原数值

    if len(filled) >= 2:
        vmin, vmax = to_k(*filled[0]), to_k(*filled[1])
    else:
        vmin = vmax = to_k(*filled[0])

    if is_year:
        vmin, vmax = round(vmin / 12, 2), round(vmax / 12, 2)

    return round(vmin, 2), round(vmax, 2)


def main():
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
    db.commit()

    success, failed, unparsed_samples = 0, 0, []
    with open('fresh_job_data.csv', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            salary_min, salary_max = parse_salary(row.get('salary_raw', ''))
            if salary_min == 0 and salary_max == 0 and row.get('salary_raw') not in ('', '面议'):
                unparsed_samples.append(row.get('salary_raw'))

            item = (
                row.get('post', ''),
                row.get('company', ''),
                row.get('address', ''),
                salary_min,
                salary_max,
                row.get('dateT', ''),
                row.get('edu', ''),
                row.get('exper', ''),
                '',
            )
            try:
                cursor.execute(
                    "insert into data (post,company,address,salary_min,salary_max,"
                    "dateT,edu,exper,content) values(?,?,?,?,?,?,?,?,?)",
                    item
                )
                success += 1
            except Exception as e:
                print('插入失败:', row, e)
                failed += 1

    db.commit()
    db.close()
    print(f'导入完成: 成功 {success} 条, 失败 {failed} 条')
    if unparsed_samples:
        print(f'有 {len(unparsed_samples)} 条薪资字符串解析为0,样例(用于检查是否有没覆盖的格式):')
        for s in unparsed_samples[:10]:
            print('  ', s)


if __name__ == '__main__':
    main()
