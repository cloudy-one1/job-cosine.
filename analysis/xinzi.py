"""
薪资分布统计。

将 (salary_min + salary_max) / 2 分桶到固定区间,返回每个桶的数量。
用于 /chart 页面渲染薪资分布图表。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        print('query failed:', e)
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
    labels = ['<5k', '5-8k', '8-11k', '11-14k', '14-17k', '17-20k', '20-23k', '23k+']

    groups = pd.cut(data, bins, labels=labels, right=False)
    counts = groups.value_counts().reindex(labels)

    return [int(counts.get(label, 0)) for label in labels]


if __name__ == '__main__':
    print(xinzi())
