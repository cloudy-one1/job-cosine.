"""
把 job_data.csv(650条真实的51job职位数据,来源见文件末尾说明)
解析后写入MySQL,字段结构沿用教材4.4.4节 write_db() 的设计:
post, company, address, salary_min, salary_max, dateT, edu, exper, content

跟教材爬虫方案的区别(诚实标注,方便你写进报告):
1. company(公司名) —— 原始数据集没有这个字段,统一留空 ''
2. dateT(发布日期) —— 原始数据集没有逐条发布日期,统一填一个快照标记
   "2024-09(数据集快照)",在报告里说明这是静态数据集,不是逐条真实发布日期
3. edu(学历)、exper(经验) —— 原始数据集这两项信息嵌在非结构化文本里,
   无法保证与职位记录可靠对应(详见我们之前的分析),所以这里统一留空 ''。
   后续可视化模块改用 region.py(地区占比) 和 jobtitle.py(职位类别占比)
   替代教材原来的 xueli.py(学历) 和 jinyan.py(经验)。

用法(SQLite版,不需要装数据库、不需要账号密码):
    1. 确认本地有新版 config.py(SQLite版,跟本文件放一起)
    2. python import_job_dataset.py
    3. 运行后目录下会自动生成一个 data.db 文件,这就是数据库
"""

import re
import csv
import sqlite3
import config  # 新版config.py(SQLite),需要和本脚本放在同一目录


def parse_salary(raw):
    """
    把原始薪资字符串解析成 (salary_min, salary_max),单位统一为"千元/月"。
    覆盖的格式(实测过这650条数据,基本覆盖所有情况):
        "2.5-5万/月"   -> (25.0, 50.0)
        "6-8千/月"     -> (6.0, 8.0)
        "10-20万/年"   -> (8.33, 16.67)   # 万/年 换算成 千/月: /12
        "248元/天"     -> (7.68, 7.68)    # 元/天 换算成 千/月: *31/1000
        ""或异常格式    -> (0.0, 0.0)
    """
    if not raw:
        return 0.0, 0.0

    nums = re.findall(r'\d+\.?\d*', raw)
    if len(nums) == 0:
        return 0.0, 0.0

    if '万/月' in raw:
        if len(nums) >= 2:
            return round(float(nums[0]) * 10, 2), round(float(nums[1]) * 10, 2)
        v = round(float(nums[0]) * 10, 2)
        return v, v

    if '千/月' in raw:
        if len(nums) >= 2:
            return round(float(nums[0]), 2), round(float(nums[1]), 2)
        v = round(float(nums[0]), 2)
        return v, v

    if '万/年' in raw:
        if len(nums) >= 2:
            return (round(float(nums[0]) * 10 / 12, 2),
                     round(float(nums[1]) * 10 / 12, 2))
        v = round(float(nums[0]) * 10 / 12, 2)
        return v, v

    if '元/天' in raw:
        v = round(float(nums[0]) * 31 / 1000, 2)
        return v, v

    # 出现没见过的格式,先返回0,0,方便你后续检查是不是漏了某种格式
    return 0.0, 0.0


def create_table_if_not_exists(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post TEXT,
            company TEXT,
            address TEXT,
            salary_min REAL,
            salary_max REAL,
            dateT TEXT,
            edu TEXT,
            exper TEXT,
            content TEXT
        )
    """)


def main():
    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()
    create_table_if_not_exists(cursor)

    # 每次导入前清空旧数据,跟教材 4.4.6 data_clr() 的思路一致
    cursor.execute("DELETE FROM data")
    db.commit()

    success, failed = 0, 0
    with open('job_data.csv', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                failed += 1
                continue
            salary_raw, post, address = row[0], row[1], row[2]
            salary_min, salary_max = parse_salary(salary_raw)

            item = (
                post,
                '',                          # company: 数据集不含此字段
                address,
                salary_min,
                salary_max,
                '2024-09(数据集快照)',         # dateT: 数据集不含逐条发布日期
                '',                          # edu: 改用 region.py 承接可视化
                '',                          # exper: 改用 jobtitle.py 承接可视化
                '',                          # content: 数据集不含详情正文
            )
            try:
                cursor.execute(
                    "insert into data (post,company,address,salary_min,salary_max,"
                    "dateT,edu,exper,content) values(?,?,?,?,?,?,?,?,?)",
                    item
                )
                success += 1
            except Exception as e:
                print('插入失败:', row, '原因:', e)
                failed += 1

    db.commit()
    cursor.close()
    db.close()
    print(f'导入完成: 成功 {success} 条, 失败 {failed} 条')
    print(f'数据库文件位置: {config.DB_PATH}')


if __name__ == '__main__':
    main()

# ------------------------------------------------------------------
# 数据来源说明(写进报告时可以直接引用):
# job_data.csv 来源于 GitHub 开源项目 chenjiandongx/51job-spider
# (MIT 协议),作者于历史时间点爬取了51job上带"Python"关键词的
# 招聘信息,覆盖北京/上海/深圳/广州,共650条,字段为:薪资范围/职位名称/地区。
# 本项目验证教材原配套爬虫方案因网站新增WAF防护已失效后(见附录验证记录),
# 采用该公开数据集替代实时爬虫作为数据来源,聚焦于Agent模块的设计与实现。
# ------------------------------------------------------------------
