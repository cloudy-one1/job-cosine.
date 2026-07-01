"""
建模层核心逻辑单元测试 — 使用合成数据，不依赖数据库。

覆盖:
  * job_clustering.choose_best_k() — 轮廓系数选 k
  * job_clustering.run_clustering() — 聚类全流程 (mock DB)
  * salary_predict.predict_salary_safe() — 安全预测 + 警告
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np


# ============================================================
# choose_best_k() — 轮廓系数选 k
# ============================================================
class TestChooseBestK:
    """用合成数据验证轮廓系数 k 值选择。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modeling.job_clustering import choose_best_k as _cbk
        self.cbk = _cbk

    def test_single_sample_returns_k1(self):
        """只有1个样本时返回 k=1。"""
        X = np.array([[0.1, 0.2]])
        k, scores = self.cbk(X)
        assert k == 1
        assert scores == {1: 0.0}

    def test_two_samples_returns_k1(self):
        """2个样本退化为 k=1 (max_k < 2)。"""
        X = np.array([[0.1, 0.2], [0.3, 0.4]])
        k, scores = self.cbk(X)
        assert k == 1

    def test_choose_k_with_clear_clusters(self):
        """3簇清晰数据应选 k=3 (或相近值)。"""
        np.random.seed(42)
        c1 = np.random.normal(0, 0.3, (30, 5))
        c2 = np.random.normal(5, 0.3, (30, 5))
        c3 = np.random.normal(10, 0.3, (30, 5))
        X = np.vstack([c1, c2, c3])
        k, scores = self.cbk(X)
        assert k >= 1
        assert len(scores) > 0
        # 在清晰3簇数据上,预期 k >= 2 (至少应发现多个簇)
        assert k >= 2

    def test_scores_are_positive(self):
        """轮廓系数应在合理范围内。"""
        np.random.seed(1)
        X = np.random.normal(0, 1, (40, 5))
        k, scores = self.cbk(X)
        for s in scores.values():
            assert -1.0 <= s <= 1.0


# ============================================================
# run_clustering() — 聚类全流程 (mock get_posts)
# ============================================================
class TestRunClustering:
    """mock 掉数据库调用,只测试聚类逻辑。"""

    def test_run_with_mocked_posts(self, monkeypatch):
        """用30个模拟职位标题运行完整聚类流程。"""
        mock_posts = [
            'Python后端开发工程师',
            'Java后端开发',
            'Go后台开发',
            '后端高级工程师',
            '后端服务端开发',
            # ---
            'Web前端工程师',
            '前端开发工程师',
            'React前端',
            'Vue前端开发',
            'Web前端高级',
            # ---
            '数据挖掘工程师',
            '大数据开发',
            '数据分析师',
            '数据工程师',
            '数据科学家',
            # ---
            '软件测试工程师',
            '自动化测试',
            '测试开发',
            '功能测试',
            '性能测试工程师',
            # ---
            '运维工程师',
            '运维开发',
            'Linux系统运维', 
            'DevOps工程师',
            'SRE运维',
            # ---
            'Python爬虫工程师',
            '数据爬虫',
            '爬虫开发',
            '网络爬虫',
            '反爬虫工程师',
        ]

        from modeling import job_clustering
        monkeypatch.setattr(job_clustering, 'get_posts', lambda: mock_posts)

        result = job_clustering.run_clustering()
        assert 'k' in result
        assert 'clusters' in result
        assert result['k'] >= 1
        assert len(result['clusters']) == result['k']
        for c in result['clusters']:
            assert 'cluster_id' in c
            assert 'auto_label' in c
            assert 'count' in c
            assert 'top_keywords' in c
            assert c['count'] > 0


# ============================================================
# predict_salary_safe() — 安全预测 + 模糊匹配警告
# ============================================================
class TestPredictSalarySafe:
    """验证 predict_salary_safe 的模糊匹配和警告机制。"""

    def test_unknown_edu_triggers_warning(self, monkeypatch):
        """输入训练数据中未见的学历应触发警告并回退。"""
        from modeling import salary_predict
        # Mock model — 不会真的调用 model.predict
        class FakeModel:
            def predict(self, X):
                return np.array([15.0])
        model = FakeModel()
        valid_edu = ['本科', '大专', '不限']
        valid_exper = ['1-3年', '3-5年', '经验不限']

        pred, matched_edu, matched_exper, warnings = (
            salary_predict.predict_salary_safe(
                model, '北京', '后端开发', '博士', '10年以上',
                valid_edu, valid_exper,
            )
        )
        assert pred == 15.0
        assert matched_edu == '不限'  # 回退到默认
        assert matched_exper == '经验不限'  # 回退到默认
        assert len(warnings) > 0

    def test_known_values_no_warnings(self):
        """训练集中存在的值不应触发任何警告。"""
        import numpy as np
        from modeling import salary_predict

        class FakeModel:
            def predict(self, X):
                return np.array([20.0])

        model = FakeModel()
        valid_edu = ['本科', '大专', '硕士']
        valid_exper = ['1-3年', '3-5年']

        pred, matched_edu, matched_exper, warnings = (
            salary_predict.predict_salary_safe(
                model, '北京', '后端开发', '本科', '3-5年',
                valid_edu, valid_exper,
            )
        )
        assert pred == 20.0
        assert matched_edu == '本科'
        assert matched_exper == '3-5年'
        assert warnings == []

    def test_unknown_city_warns(self):
        """未见过的城市也应触发警告。"""
        import numpy as np
        from modeling import salary_predict

        class FakeModel:
            def predict(self, X):
                return np.array([10.0])

        model = FakeModel()
        valid_city = ['北京', '上海']

        pred, _, _, warnings = salary_predict.predict_salary_safe(
            model, '拉萨', '后端开发', '本科', '3-5年',
            ['本科'], ['3-5年'],
            valid_city=valid_city,
        )
        assert any('拉萨' in w for w in warnings)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
