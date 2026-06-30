"""
职位类别占比统计 —— 替换原来"工作年限要求"饼图的位置。

教材原 jinyan.py 是 SELECT exper FROM data 做 value_counts();
这里改成 SELECT post FROM data,用一套自定义、写在代码里、完全可复现的
关键词规则对职位名称分类,再做同样的 value_counts() 统计。

分类规则按下面顺序匹配(命中第一个就归类,没命中任何关键词归入"通用开发"):
    爬虫 -> 爬虫工程师
    架构师 -> 架构师
    讲师 -> 培训讲师
    实习 -> 实习生
    测试 -> 测试工程师
    运维 -> 运维工程师
    数据|挖掘|大数据 -> 数据相关
    后端|后台|服务端 -> 后端开发
    web|前端 (不区分大小写) -> Web开发
    高级|资深|中级 -> 高级/资深开发
    默认 -> 通用开发

这套规则你可以根据实际数据再调整,关键是写进报告时要能讲清楚分类依据是什么。
"""
import sqlite3
import config
from pandas import DataFrame

RULES = [
    ('爬虫', '爬虫工程师'),
    ('架构师', '架构师'),
    ('讲师', '培训讲师'),
    ('实习', '实习生'),
    ('测试', '测试工程师'),
    ('运维', '运维工程师'),
    ('数据', '数据相关'),
    ('挖掘', '数据相关'),
    ('大数据', '数据相关'),
    ('后端', '后端开发'),
    ('后台', '后端开发'),
    ('服务端', '后端开发'),
    ('web', 'Web开发'),
    ('前端', 'Web开发'),
    ('高级', '高级/资深开发'),
    ('资深', '高级/资深开发'),
    ('中级', '高级/资深开发'),
]


def classify(post_title):
    title_lower = post_title.lower()
    for keyword, category in RULES:
        if keyword.lower() in title_lower:
            return category
    return '通用开发'


def get_post():
    db = sqlite3.connect(config.DB_PATH)
    try:
        cursor = db.cursor()
        cursor.execute("select post from data")
        result = cursor.fetchall()
        return result
    except Exception as e:
        print('查询失败:', e)
        return []
    finally:
        db.close()


def jobtitlefun():
    rows = get_post()
    categories = [classify(row[0]) for row in rows if row[0]]

    data = DataFrame(categories)
    counts = data[0].value_counts()

    list_all = []
    for category, count in zip(counts.index, counts):
        list_all.append([category, int(count)])
    return list_all


if __name__ == '__main__':
    print(jobtitlefun())
