"""
学历分析 —— 教材4.5.4节 xueli.py 的真正实现。
之前用 region.py(地区分析)替代这个位置,是因为旧数据集没有真实学历字段;
现在新采集的数据里 edu 字段是真实值,这个模块可以恢复成教材原本想做的样子。
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
        print('查询失败:', e)
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
