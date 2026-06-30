"""
城市/地区分布统计。

从 address 字段按 '-' 分割提取城市,然后按城市统计出现次数。
返回 [[城市名, 数量], ...] 按频率从大到小排序。
用于 /chart 页面渲染地区饼图。
"""
import sqlite3
import config
from pandas import DataFrame


def get_address():
    db = sqlite3.connect(config.DB_PATH)
    try:
        cursor = db.cursor()
        cursor.execute("select address from data")
        return cursor.fetchall()
    except Exception as e:
        print('query failed:', e)
        return []
    finally:
        db.close()


def regionfun():
    rows = get_address()
    city_list = []
    for row in rows:
        addr = row[0]
        city = addr.split('-')[0] if addr else 'Unknown'
        city_list.append(city)

    counts = DataFrame(city_list)[0].value_counts()

    list_all = []
    for city, count in zip(counts.index, counts):
        list_all.append([city, int(count)])
    return list_all


if __name__ == '__main__':
    print(regionfun())
