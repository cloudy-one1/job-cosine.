"""
职位类别聚类(KMeans) —— 跟 jobtitle.py 的规则匹配方法形成对比。

两种方法的本质区别(写报告/答�antml辩时可以直接用这段对比):
- jobtitle.py: 人工预设关键词规则("包含'爬虫'就归为爬虫工程师"),
  优点是可解释、可控;缺点是类别由人主观定义,没有用到数据本身的结构。
- 本文件: 不预设任何类别,让KMeans从职位名称的文本特征里自己"发现"
  聚类结构;优点是数据驱动;缺点是聚类出来的"类别"需要人工看关键词
  才能理解它实际代表什么,可解释性比规则方法差。

技术流程:
1. jieba 对职位名称做中文分词
2. TF-IDF 把分词结果转成数值向量(每个词的重要程度)
3. KMeans 把这些向量分成 k 组
4. 每组挑出TF-IDF权重最高的几个词,作为这一组的"自动标签"
   (因为KMeans本身只给出"第几组",不会告诉你这组代表什么,
   这一步是为了让聚类结果变得可读)

k 的选择:用轮廓系数(silhouette score)在 4~11 之间扫一遍,
选分数最高的 k,而不是随手指定一个数字。
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

# 标点符号 + 在这份"全是python岗位"的数据里几乎每条都出现、没有区分度的词
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
    """
    用轮廓系数选k,而不是随手定一个数字。

    k_range默认是4~11,但如果样本数太少(比如一次实时采集只抓到几条数据),
    会动态把上限降到"样本数-1"以内,避免KMeans直接报错崩溃
    (这是实测踩到的真实边界情况: 采集结果很少时整个/collect请求会500)。

    另外,即使k设置合理,如果样本里的文本特征太相似(小样本时常见),
    KMeans实际收敛出来的类别数可能比设定的k更少,导致只剩1类——
    这种"退化"情况下轮廓系数算不出来(silhouette_score要求至少2个
    不同类别),这里直接跳过这个k,而不是让程序崩溃。
    """
    n_samples = X.shape[0]
    max_k = min(11, n_samples - 1)

    if max_k < 2:
        # 样本太少(比如只有1-2条),没法做有意义的聚类,直接返回k=1
        return 1, {1: 0.0}

    if k_range is None:
        k_range = range(min(4, max_k), max_k + 1)

    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X)
        n_distinct = len(set(labels))
        if n_distinct < 2 or n_distinct > n_samples - 1:
            continue  # 这个k实际退化了,跳过,不计算轮廓系数
        scores[k] = silhouette_score(X, labels)

    if not scores:
        # 所有k都退化了(样本太少或文本太相似,聚类没有意义),退回k=1
        return 1, {1: 0.0}

    best_k = max(scores, key=scores.get)
    return best_k, scores


def run_clustering(k=None):
    posts = get_posts()
    # min_df=2 要求一个词至少在2篇文档里出现才纳入词表,样本量正常时这样能
    # 过滤掉只出现一次的噪声词;但样本太少时(比如一次实时采集只抓到几条),
    # 这个要求可能完全无法满足,导致报错,这里动态降级成min_df=1
    min_df = 2 if len(posts) >= 20 else 1
    vectorizer = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, min_df=min_df)
    X = vectorizer.fit_transform(posts)
    feature_names = vectorizer.get_feature_names_out()

    if k is None:
        k, k_scores = choose_best_k(X)
    else:
        k_scores = None

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
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
    print(f"自动选出的最佳聚类数 k = {output['k']}")
    if output['k_scores']:
        print('各k值对应的轮廓系数(越接近1越好,这份数据规模小,普遍不会很高):')
        for k, score in output['k_scores'].items():
            print(f'  k={k}: {score:.3f}')
    print('\n聚类结果(按数量从多到少排序):')
    for c in output['clusters']:
        print(f"  簇{c['cluster_id']} [自动标签: {c['auto_label']}] "
              f"数量={c['count']} 关键词={c['top_keywords']}")
