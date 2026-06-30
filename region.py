"""
地区占比统计 —— 复用教材 4.5.2 节 map.py 的统计逻辑(SELECT address FROM data,
按'-'拆分取城市,value_counts() 统计),用来填充原本"学历占比情况"饼图的位置。

跟教材 xueli.py 的返回格式保持一致: [[城市名, 数量], [城市名, 数量], ...]
方便直接套用 h.html 里现成的 Highcharts 饼图代码,只需把变量名/标题改一下。
(SQLite版,替代原pymysql连接方式)
"""
import sqlite3
import config
from pandas import DataFrame


def get_address():
    db = sqlite3.connect(config.DB_PATH)
    try:
        cursor = db.cursor()
        cursor.execute("select address from data")
        result = cursor.fetchall()
        return result
    except Exception as e:
        print('查询失败:', e)
        return []
    finally:
        db.close()


def regionfun():
    """统计各城市的职位数量占比(教材 map.py 的逻辑,原样保留)"""
    rows = get_address()
    city_list = []
    for row in rows:
        addr = row[0]
        city = addr.split('-')[0] if addr else '未知'
        city_list.append(city)

    data = DataFrame(city_list)
    counts = data[0].value_counts()

    list_all = []
    for city, count in zip(counts.index, counts):
        list_all.append([city, int(count)])
    return list_all


if __name__ == '__main__':
    print(regionfun())
