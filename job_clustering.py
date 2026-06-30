"""
职位标题无监督聚类。

处理流程:jieba 中文分词 -> TF-IDF 向量化 -> 使用轮廓系数选择 k 值的 KMeans 聚类 ->
输出每个聚类的高权重关键词摘要。

特意采用轻量化、纯 sklearn 实现。典型采集数据约 <1000 行,更复杂的模型反而容易过拟合。
主要耗时在 jieba 分词与轮廓系数计算,两者均在 Flask 启动时预计算并缓存,避免页面刷新时重复运算。
"""
import sqlite3
import config
import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


def get_posts():
    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()
    cursor.execute("SELECT post FROM data")
    rows = [r[0] for r in cursor.fetchall() if r[0]]
    db.close()
    return rows


import re

# 几乎每个职位都会出现的高频词,对分类无贡献。
# 同时包含标点符号,由下方正则表达式过滤。
STOPWORDS = {
    'python', '工程师', '开发', '软件', '(', ')', '（', '）', '/', '、',
    '-', '－', '岗位', '招聘', '需求', '相关', '方向', '人员',
}
PUNCT_PATTERN = re.compile(r'^[\W_]+$')


def tokenize(text):
    text_lower = text.lower()
    words = jieba.cut(text_lower)
    result = []
    for w in words:
        w = w.strip()
        if not w or w in STOPWORDS:
            continue
        if PUNCT_PATTERN.match(w):
            continue
        result.append(w)
    return result


def choose_best_k(X, k_range=None):
    """遍历候选 k 值,选择轮廓系数最高的一个。

    当样本数过小或每次聚类都退化为单簇时,回退到 k=1(无有意义的聚类)。
    这两种情况在小范围采集运行中常出现,必须妥善处理以免程序崩溃。
    """
    n_samples = X.shape[0]
    max_k = min(11, n_samples - 1)

    if max_k < 2:
        return 1, {1: 0.0}

    if k_range is None:
        k_range = range(min(4, max_k), max_k + 1)

    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init='auto')
        labels = km.fit_predict(X)
        n_distinct = len(set(labels))
        if n_distinct < 2 or n_distinct > n_samples - 1:
            continue
        scores[k] = silhouette_score(X, labels)

    if not scores:
        return 1, {1: 0.0}

    best_k = max(scores, key=scores.get)
    return best_k, scores


def run_clustering(k=None):
    posts = get_posts()
    # 正常大小数据使用 min_df=2 过滤稀有词;当数据集很小时(例如非常新、非常窄范围的一次采集),
    # 放宽为 min_df=1,保证向量化器仍能输出有效结果。
    min_df = 2 if len(posts) >= 20 else 1
    vectorizer = TfidfVectorizer(tokenizer=tokenize, min_df=min_df)
    X = vectorizer.fit_transform(posts)
    feature_names = vectorizer.get_feature_names_out()

    if k is None:
        k, k_scores = choose_best_k(X)
    else:
        k_scores = None

    km = KMeans(n_clusters=k, random_state=42, n_init='auto')
    labels = km.fit_predict(X)

    result = []
    for i in range(k):
        idx = np.where(labels == i)[0]
        count = len(idx)
        center = km.cluster_centers_[i]
        top_idx = center.argsort()[-5:][::-1]
        top_keywords = [feature_names[j] for j in top_idx]
        result.append({
            'cluster_id': i,
            'auto_label': '/'.join(top_keywords[:3]),
            'count': int(count),
            'top_keywords': top_keywords,
        })
    result.sort(key=lambda x: -x['count'])
    return {'k': k, 'k_scores': k_scores, 'clusters': result}


if __name__ == '__main__':
    output = run_clustering()
    print(f"自动选择的聚类数 k = {output['k']}")
    if output['k_scores']:
        print('每个候选 k 的轮廓系数:')
        for k, score in output['k_scores'].items():
            print(f'  k={k}: {score:.3f}')
    print('\n聚类结果(按规模从大到小):')
    for c in output['clusters']:
        print(f"  聚类 {c['cluster_id']} [标签: {c['auto_label']}] "
              f"数量={c['count']} 关键词={c['top_keywords']}")
