"""
工作经验要求分布统计。

统计 data 表中每个不同 exper 值的出现次数,返回 [[标签, 数量], ...]
按频率从大到小排序。空值合并为 "经验不限"。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import config
from pandas import DataFrame


def get_exper():
    db = sqlite3.connect(config.DB_PATH)
    try:
        cursor = db.cursor()
        cursor.execute("select exper from data")
        return cursor.fetchall()
    except Exception as e:
        print('query failed:', e)
        return []
    finally:
        db.close()


def jinyanfun():
    rows = get_exper()
    data = [r[0] for r in rows if r[0]]
    data = [d if d else '经验不限' for d in data]

    counts = DataFrame(data)[0].value_counts()
    list_all = []
    for exper, count in zip(counts.index, counts):
        list_all.append([exper, int(count)])
    return list_all


if __name__ == '__main__':
    print(jinyanfun())
