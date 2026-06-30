"""
Agent 工具集 —— 每个函数对应Agent能调用的一个"工具"。
设计原则:只暴露我们数据库里真实存在、可靠的字段(post/address/salary/category),
不编造数据集里没有的信息(比如公司名、岗位要求正文)。
"""
import sqlite3
import config
from jobtitle import classify
from xueli import xuelifun
from jinyan import jinyanfun
from salary_predict import train_and_evaluate, predict_salary_safe as _predict_salary_safe

# 模型只在模块加载时训练一次,避免每次调用工具都重新训练
_model_result = train_and_evaluate()


def edu_overview() -> list:
    """获取学历分布总览(本科/大专/硕士等占比),不需要参数。参数: 无"""
    return [{'edu': e, 'count': c} for e, c in xuelifun()]


def exper_overview() -> list:
    """获取工作经验要求分布总览,不需要参数。参数: 无"""
    return [{'exper': e, 'count': c} for e, c in jinyanfun()]


def predict_salary(city: str, category: str, edu: str = '不限', exper: str = '经验不限') -> dict:
    """
    用训练好的线性回归模型,预测某城市+职位类别+学历+经验组合的薪资。
    跟 query_jobs 直接查历史平均值不同,这个是模型预测值,
    对样本较少的组合,预测会比直接平均更平滑(也可能更不准,
    这是线性回归的特点,数据量小的时候两种方法谁更准不一定)。
    """
    pred, matched_edu, matched_exper, warns = _predict_salary_safe(
        _model_result['model'], city, category, edu, exper,
        _model_result['valid_edu'], _model_result['valid_exper'],
    )
    result = {
        'city': city,
        'category': category,
        'edu': matched_edu,
        'exper': matched_exper,
        'predicted_salary_k': pred,
        'model_r2': round(_model_result['r2'], 2),
        'note': f"模型R²={_model_result['r2']:.2f}(加入学历经验前为{_model_result['old_r2']:.2f}),数据量有限,该预测仅供参考",
    }
    if warns:
        result['input_warnings'] = warns
    return result


def _connect():
    return sqlite3.connect(config.DB_PATH)


def query_jobs(keyword: str) -> dict:
    """
    按职位名称关键词模糊查询,返回匹配数量、薪资统计、城市分布。
    例如 keyword='爬虫' 会匹配所有职位名称包含"爬虫"的记录。
    """
    db = _connect()
    cursor = db.cursor()
    cursor.execute(
        "SELECT post, address, salary_min, salary_max FROM data WHERE post LIKE ?",
        (f'%{keyword}%',)
    )
    rows = cursor.fetchall()
    db.close()

    if not rows:
        return {'keyword': keyword, 'count': 0, 'message': '没有找到匹配的职位'}

    salaries = [(r[2] + r[3]) / 2 for r in rows if r[2] or r[3]]
    cities = {}
    for r in rows:
        city = r[1].split('-')[0] if r[1] else '未知'
        cities[city] = cities.get(city, 0) + 1
    top_cities = sorted(cities.items(), key=lambda x: -x[1])[:3]

    return {
        'keyword': keyword,
        'count': len(rows),
        'avg_salary_k': round(sum(salaries) / len(salaries), 1) if salaries else 0,
        'min_salary_k': round(min(salaries), 1) if salaries else 0,
        'max_salary_k': round(max(salaries), 1) if salaries else 0,
        'top_cities': top_cities,
    }


def category_overview() -> list:
    """
    返回所有职位类别(通用开发/后端开发/爬虫工程师等)及对应数量、平均薪资。
    """
    db = _connect()
    cursor = db.cursor()
    cursor.execute("SELECT post, salary_min, salary_max FROM data")
    rows = cursor.fetchall()
    db.close()

    cat_data = {}
    for post, smin, smax in rows:
        cat = classify(post)
        cat_data.setdefault(cat, []).append((smin + smax) / 2 if (smin or smax) else 0)

    result = []
    for cat, salaries in sorted(cat_data.items(), key=lambda x: -len(x[1])):
        valid = [s for s in salaries if s > 0]
        avg = round(sum(valid) / len(valid), 1) if valid else 0
        result.append({'category': cat, 'count': len(salaries), 'avg_salary_k': avg})
    return result


def city_overview() -> list:
    """返回各城市的职位数量和平均薪资"""
    db = _connect()
    cursor = db.cursor()
    cursor.execute("SELECT address, salary_min, salary_max FROM data")
    rows = cursor.fetchall()
    db.close()

    city_data = {}
    for addr, smin, smax in rows:
        city = addr.split('-')[0] if addr else '未知'
        city_data.setdefault(city, []).append((smin + smax) / 2 if (smin or smax) else 0)

    result = []
    for city, salaries in sorted(city_data.items(), key=lambda x: -len(x[1])):
        valid = [s for s in salaries if s > 0]
        avg = round(sum(valid) / len(valid), 1) if valid else 0
        result.append({'city': city, 'count': len(salaries), 'avg_salary_k': avg})
    return result


# 工具注册表:Agent循环根据这个字典知道有哪些工具可以调用
TOOLS = {
    'query_jobs': {
        'func': query_jobs,
        'description': '按关键词搜索职位(如"爬虫"/"后端"/"测试"),返回数量/薪资/城市分布。参数: keyword(字符串)',
    },
    'category_overview': {
        'func': category_overview,
        'description': '获取全部职位类别的分布和平均薪资总览,不需要参数。参数: 无',
    },
    'city_overview': {
        'func': city_overview,
        'description': '获取各城市的职位数量和平均薪资总览,不需要参数。参数: 无',
    },
    'edu_overview': {
        'func': edu_overview,
        'description': '获取学历要求分布总览(本科/大专/硕士等占比),不需要参数。参数: 无',
    },
    'exper_overview': {
        'func': exper_overview,
        'description': '获取工作经验要求分布总览,不需要参数。参数: 无',
    },
    'predict_salary': {
        'func': predict_salary,
        'description': '用回归模型预测某城市+职位类别+学历+经验组合的薪资。参数: city(字符串,如"北京"), category(字符串,如"爬虫工程师"等), edu(可选,字符串,如"本科"), exper(可选,字符串,如"3-5年")',
    },
}


if __name__ == '__main__':
    print('=== query_jobs("爬虫") ===')
    print(query_jobs('爬虫'))
    print('\n=== category_overview() (前5) ===')
    for item in category_overview()[:5]:
        print(item)
    print('\n=== city_overview() ===')
    for item in city_overview():
        print(item)
    print('\n=== predict_salary("北京", "爬虫工程师", "本科", "3-5年") ===')
    print(predict_salary('北京', '爬虫工程师', '本科', '3-5年'))
    print('\n=== edu_overview() ===')
    print(edu_overview())
    print('\n=== exper_overview() ===')
    print(exper_overview())

