"""
职位标题分类。

对 data 表中的每个 post 值应用关键词优先匹配规则集,统计得到的类别,
返回 [[类别, 数量], ...] 按频率从大到小排序。classify 辅助函数也被
salary_predict 模块用于生成线性回归模型的 category 特征。

分类逻辑设计简单:每个职位按顺序匹配关键词,并打上第一个触发的类别标签。
没有匹配到任何关键词的职位回退到 "通用开发"。

规则列表是模块级常量,便于阅读者快速了解分类体系,也便于修改而无需理解
周边代码。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    """使用 RULES 为单个职位标题分配类别标签。"""
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
        return cursor.fetchall()
    except Exception as e:
        print('query failed:', e)
        return []
    finally:
        db.close()


def jobtitlefun():
    rows = get_post()
    categories = [classify(row[0]) for row in rows if row[0]]

    counts = DataFrame(categories)[0].value_counts()

    list_all = []
    for category, count in zip(counts.index, counts):
        list_all.append([category, int(count)])
    return list_all


if __name__ == '__main__':
    print(jobtitlefun())
