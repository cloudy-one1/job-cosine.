"""
CSV 导入工具。读取项目目录中的 fresh_job_data.csv(原始 51job 快照),
解析每行内容并写入 SQLite 的 data.db。

方便用户不必进行实时采集也能运行完整的分析流程。
若需要实时采集,请直接使用 python_job_scraper 模块或 /collect 路由。
"""
import re
import csv
import sqlite3
import config


def parse_salary(raw):
    """解析类似 \"1.5-2万/月\" 的薪资字符串,返回 (最低_千元, 最高_千元)。
    无法解析时返回 (0.0, 0.0)。

    处理的格式包括:
    * 面议 / 空                 -> (0.0, 0.0)
    * 1.5-2万/月                -> (15.0, 20.0)
    * 8千-1.2万/月              -> (8.0, 12.0)  (单位混合)
    * 15-25万/年                -> (12.5, 20.8)  (年薪转月薪)
    * 10-20千/月                -> (10.0, 20.0)
    * 1万以上/月                -> 按单个值处理
    * 3千-4.5千/月              -> (3.0, 4.5)

    关键设计:中文薪资简写通常只在范围末尾写一次单位(如 \"1.5-2万\")。
    这里从左到右遍历所有数字,缺失单位的数字从最近一个带有单位的数字继承单位。
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

    # 反向填充缺失单位:没显式单位的数字继承后续最近数字的单位
    filled = []
    last_unit = None
    for num, unit in reversed(matches):
        if unit:
            last_unit = unit
        filled.append((num, unit or last_unit))
    filled.reverse()

    def to_k(num_str, unit):
        v = float(num_str)
        return v * 10 if unit == '万' else v

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
                print('insert failed:', row, e)
                failed += 1

    db.commit()
    db.close()
    print(f'导入完成:成功 {success} 条,失败 {failed} 条')
    if unparsed_samples:
        print(f'{len(unparsed_samples)} 条薪资字符串解析为 0(调试样本):')
        for s in unparsed_samples[:10]:
            print('  ', s)


if __name__ == '__main__':
    main()
