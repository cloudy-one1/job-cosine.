"""
薪资预测模型。

基于 (城市, 职位类别, 学历, 经验) 元组训练线性回归。模型特意设计得简单:
训练数据约 500 行级别,比线性回归更复杂的模型会严重过拟合。

训练两个版本模型进行对比:
* 仅使用 city + category (基线模型)
* 使用 city + category + education + experience (全特征集)

报告 R² 的提升(或无提升),以便调用方判断学历和经验字段是否为当前数据集增加预测信号。
"""
import sqlite3
import config
from jobtitle import classify
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score, mean_absolute_error


def get_rows():
    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()
    cursor.execute("SELECT post, address, salary_min, salary_max, edu, exper FROM data")
    rows = cursor.fetchall()
    db.close()
    return rows


def build_dataset(include_edu_exper=True):
    rows = get_rows()
    X, y = [], []
    for post, addr, smin, smax, edu, exper in rows:
        if not smin and not smax:
            continue
        city = addr.split('-')[0] if addr else 'Unknown'
        category = classify(post)
        avg_salary = (smin + smax) / 2
        if include_edu_exper:
            X.append([city, category, edu or '不限', exper or '经验不限'])
        else:
            X.append([city, category])
        y.append(avg_salary)
    return np.array(X, dtype=object), np.array(y)


def build_model(n_features):
    return Pipeline([
        ('prep', ColumnTransformer([
            ('cat', OneHotEncoder(handle_unknown='ignore'), list(range(n_features))),
        ])),
        ('reg', LinearRegression()),
    ])


def _train_one(include_edu_exper, random_state=42):
    X, y = build_dataset(include_edu_exper)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state
    )
    model = build_model(X.shape[1])
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    baseline_pred = np.full_like(y_test, y_train.mean())
    baseline_mae = mean_absolute_error(y_test, baseline_pred)

    return {
        'model': model, 'r2': r2, 'mae': mae, 'baseline_mae': baseline_mae,
        'n_train': len(X_train), 'n_test': len(X_test),
        'include_edu_exper': include_edu_exper,
    }


def train_and_evaluate(random_state=42):
    """训练全特征模型和基线模型。返回全特征模型的结果字典,附加基线 R² 用于对比。"""
    old_result = _train_one(include_edu_exper=False, random_state=random_state)
    new_result = _train_one(include_edu_exper=True, random_state=random_state)

    new_result['old_r2'] = old_result['r2']
    new_result['old_mae'] = old_result['mae']

    # 记录训练时观察到的类别水平,以便下游调用方在请求值未见过时发出警告
    X, _ = build_dataset(include_edu_exper=True)
    new_result['valid_edu'] = sorted(set(X[:, 2]))
    new_result['valid_exper'] = sorted(set(X[:, 3]))
    return new_result


def predict_salary(model, city, category, edu='不限', exper='经验不限'):
    pred = model.predict(np.array([[city, category, edu, exper]], dtype=object))
    return round(float(pred[0]), 1)


def _fuzzy_match(value, valid_values, fallback):
    """返回 (匹配后的值, 是否发生替换) 元组。
    如果 value 不在 valid_values 中,尝试找到包含 value 的条目。否则回退到提供的默认值。
    """
    if not value or value in valid_values:
        return (value or fallback), False
    for v in valid_values:
        if value in v:
            return v, True
    return fallback, True


def predict_salary_safe(model, city, category, edu, exper, valid_edu, valid_exper):
    """predict_salary 的包装函数:当调用方传入训练数据中没有的学历或经验值时发出警告
    (而不是默默给出错误预测)。OneHotEncoder(handle_unknown='ignore') 会丢弃未见过的列,
    这会悄悄改变特征向量,导致用户输入数字期望匹配 "3-5年" 风格类别时产生无意义预测。
    """
    warnings = []
    matched_edu, edu_sub = _fuzzy_match(edu, valid_edu, '不限')
    matched_exper, exper_sub = _fuzzy_match(exper, valid_exper, '经验不限')
    if edu_sub:
        warnings.append(f'学历输入"{edu}"不在训练数据标准取值中,已模糊匹配/替换为"{matched_edu}"')
    if exper_sub:
        warnings.append(f'经验输入"{exper}"不在训练数据标准取值中,已模糊匹配/替换为"{matched_exper}"')

    pred = predict_salary(model, city, category, matched_edu, matched_exper)
    return pred, matched_edu, matched_exper, warnings


if __name__ == '__main__':
    result = train_and_evaluate()
    print(f"训练样本数: {result['n_train']}, 测试样本数: {result['n_test']}")
    print(f"仅使用 city + category          R²={result['old_r2']:.3f}  MAE={result['old_mae']:.2f}k 元")
    print(f"使用 city + category + 学历 + 经验  R²={result['r2']:.3f}  MAE={result['mae']:.2f}k 元")
    if result['r2'] > result['old_r2']:
        print(">> 学历与经验特征提升了 R²")
    else:
        print(">> 学历与经验特征未提升 R²")
    print(f"基线(预测为训练平均值)MAE: {result['baseline_mae']:.2f}k 元/月")

    print('\n预测示例:')
    for city, cat, edu, exp in [
        ('北京', '爬虫工程师', '本科', '3-5年'),
        ('上海', '后端开发', '大专', '1-3年'),
    ]:
        pred = predict_salary(result['model'], city, cat, edu, exp)
        print(f"  {city} + {cat} + {edu} + {exp} -> {pred}k 元/月")
