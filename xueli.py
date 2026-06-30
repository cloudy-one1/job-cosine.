"""
学历分布统计。

统计 data 表中每个不同 edu 值的出现次数,返回 [[标签, 数量], ...]
按频率从大到小排序。空值合并为 "不限"。
"""
import sqlite3
import config
from pandas import DataFrame


def get_edu():
    db = sqlite3.connect(config.DB_PATH)
    try:
        cursor = db.cursor()
        cursor.execute("select edu from data")
        return cursor.fetchall()
    except Exception as e:
        print('query failed:', e)
        return []
    finally:
        db.close()


def xuelifun():
    rows = get_edu()
    data = [r[0] for r in rows if r[0]]
    data = [d if d else '不限' for d in data]

    counts = DataFrame(data)[0].value_counts()
    list_all = []
    for edu, count in zip(counts.index, counts):
        list_all.append([edu, int(count)])
    return list_all


if __name__ == '__main__':
    print(xuelifun())
