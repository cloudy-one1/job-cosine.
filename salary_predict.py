"""
薪资预测模型 —— 用"城市 + 职位类别 + 学历 + 经验"预测薪资水平。

更新说明: 之前数据集没有真实的学历/经验字段,模型只能用城市+职位类别两个特征。
现在新采集的数据里这两项是真实值,这里同时训练"旧特征版"和"新特征版"两个模型,
对比R²的变化,用真实数字说话——而不是想当然地说"加了新特征肯定更准"。

诚实声明: 即便特征更全,650条左右的小样本+线性回归,R²仍然不会很高,
这是数据规模的客观局限,不是模型设计的问题。
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
        city = addr.split('-')[0] if addr else '未知'
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
    """
    训练两个版本: 城市+类别(旧特征) vs 城市+类别+学历+经验(新特征),
    返回新特征版本作为主模型(用于实际预测),同时保留两版的指标用于对比展示。
    """
    old_result = _train_one(include_edu_exper=False, random_state=random_state)
    new_result = _train_one(include_edu_exper=True, random_state=random_state)

    new_result['old_r2'] = old_result['r2']
    new_result['old_mae'] = old_result['mae']

    # 记录训练数据里真实出现过的学历/经验取值,供predict_salary校验用户输入。
    # 模型本身的OneHotEncoder对没见过的取值会静默忽略(handle_unknown='ignore'),
    # 不会报错,但预测结果会因为缺了这个特征的信息而变得不可靠,
    # 这是实测踩到的真实问题(比如输入"3"而不是"3-5年",会被直接忽略掉)。
    X, _ = build_dataset(include_edu_exper=True)
    new_result['valid_edu'] = sorted(set(X[:, 2]))
    new_result['valid_exper'] = sorted(set(X[:, 3]))
    return new_result


def predict_salary(model, city, category, edu='不限', exper='经验不限'):
    pred = model.predict(np.array([[city, category, edu, exper]], dtype=object))
    return round(float(pred[0]), 1)


def _fuzzy_match(value, valid_values, fallback):
    """
    如果value不在训练数据出现过的标准取值里,尝试找一个"包含value"的有效值
    (比如输入"3"匹配到"3-5年"),找不到就退回fallback。
    返回 (matched_value, 是否发生了替换)。
    """
    if not value or value in valid_values:
        return (value or fallback), False
    for v in valid_values:
        if value in v:
            return v, True
    return fallback, True


def predict_salary_safe(model, city, category, edu, exper, valid_edu, valid_exper):
    """
    带输入校验的预测包装。

    背景: OneHotEncoder(handle_unknown='ignore') 对没见过的取值是静默忽略的,
    不会报错,但会导致那个特征对预测完全不起作用,产生看起来很离谱的结果
    (实测踩到过: 输入经验"3"而不是训练数据里的"3-5年"格式,经验信息被
    整个丢弃,预测出"实习生比资深岗位薪资还高"这种不合理结果)。
    这个函数在调用模型之前,先做一次模糊匹配+给出警告,而不是让错误静默发生。
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
    print(f"旧特征(城市+类别)        R²={result['old_r2']:.3f}  MAE={result['old_mae']:.2f}千元")
    print(f"新特征(+学历+经验)       R²={result['r2']:.3f}  MAE={result['mae']:.2f}千元")
    if result['r2'] > result['old_r2']:
        print(">>> 加入学历+经验后R²提升,说明这两个特征确实带来了额外信息量")
    else:
        print(">>> 加入学历+经验后R²没有提升(甚至下降),可能是特征类别太多、样本被进一步稀释")
    print(f"基准线 MAE(直接猜平均值): {result['baseline_mae']:.2f} 千元/月")

    print('\n示例预测:')
    for city, cat, edu, exper in [
        ('北京', '爬虫工程师', '本科', '3-5年'),
        ('上海', '通用开发', '大专', '1年以下'),
    ]:
        pred = predict_salary(result['model'], city, cat, edu, exper)
        print(f"  {city}+{cat}+{edu}+{exper}: 预测薪资约 {pred} 千元/月")

