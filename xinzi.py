"""
薪资分布统计 —— 替代教材 xinzi.py。
逻辑跟教材一致(把薪资分到几个区间,统计每个区间的职位数量),
只是把MySQL连接换成SQLite,单位也对齐成我们数据库里存的"千元/月"。
"""
import sqlite3
import config
import pandas as pd


def get_salary():
    db = sqlite3.connect(config.DB_PATH)
    try:
        cursor = db.cursor()
        cursor.execute("select salary_min, salary_max from data")
        return cursor.fetchall()
    except Exception as e:
        print('查询失败:', e)
        return []
    finally:
        db.close()


def xinzi():
    rows = get_salary()
    data = []
    for smin, smax in rows:
        if smin or smax:
            data.append((smin + smax) / 2)

    bins = [0, 5, 8, 11, 14, 17, 20, 23, 999999]
    labels = ['小于5k', '5k~8k', '8k~11k', '11k~14k', '14k~17k', '17k~20k', '20k~23k', '23k以上']

    fenzu = pd.cut(data, bins, labels=labels, right=False)
    pinshu = fenzu.value_counts().reindex(labels)

    return [int(pinshu.get(label, 0)) for label in labels]


if __name__ == '__main__':
    print(xinzi())
