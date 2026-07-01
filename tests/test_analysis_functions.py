"""
分析层纯逻辑单元测试 — 不依赖数据库、不依赖网络。

覆盖:
  * analysis.jobtitle.classify()  — 关键词规则匹配
  * analysis.region.extract_city() — 城市提取
  * modeling.job_clustering.tokenize() — jieba 分词 + 去停用词
  * modeling.salary_predict._fuzzy_match() — 模糊匹配回退
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ============================================================
# classify() — 职位标题分类
# ============================================================
class TestClassify:
    """验证 classify() 关键词优先匹配规则集。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from analysis.jobtitle import classify as _cls
        self.cls = _cls

    def test_exact_match_backend(self):
        assert self.cls('后端开发工程师') == '后端开发'

    def test_exact_match_spider(self):
        assert self.cls('Python爬虫工程师') == '爬虫工程师'

    def test_exact_match_architect(self):
        assert self.cls('Java架构师') == '架构师'

    def test_exact_match_intern(self):
        assert self.cls('前端实习生') == '实习生'

    def test_exact_match_tester(self):
        assert self.cls('软件测试工程师') == '测试工程师'

    def test_exact_match_ops(self):
        assert self.cls('Linux运维工程师') == '运维工程师'

    def test_exact_match_web_frontend(self):
        assert self.cls('Web前端开发') == 'Web开发'

    def test_match_senior(self):
        """关键词'测试'在规则列表中排在'高级'之前,因此先命中。"""
        assert self.cls('高级测试工程师') == '测试工程师'

    def test_senior_dev(self):
        """不含其他关键词时,'高级'命中高级/资深开发。"""
        assert self.cls('高级Java工程师') == '高级/资深开发'

    def test_fallback_unknown(self):
        assert self.cls('产品经理') == '通用开发'

    def test_case_insensitive(self):
        assert self.cls('PYTHON爬虫') == '爬虫工程师'

    def test_data_related(self):
        assert self.cls('大数据开发工程师') == '数据相关'
        assert self.cls('数据挖掘工程师') == '数据相关'

    def test_trigram_teacher(self):
        assert self.cls('Python培训讲师') == '培训讲师'

    def test_empty_string(self):
        assert self.cls('') == '通用开发'


# ============================================================
# extract_city() — 城市提取
# ============================================================
class TestExtractCity:
    """验证从地址字符串中提取城市名。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from analysis.region import extract_city as _ec
        self.ec = _ec

    def test_standard_address(self):
        assert self.ec('北京-海淀区') == '北京'

    def test_address_with_multi_dash(self):
        assert self.ec('上海-浦东新区-张江') == '上海'

    def test_no_dash(self):
        assert self.ec('深圳') == '深圳'

    def test_empty(self):
        assert self.ec('') == 'Unknown'

    def test_none(self):
        assert self.ec(None) == 'Unknown'

    def test_english_city(self):
        assert self.ec('Remote-Anywhere') == 'Remote'


# ============================================================
# tokenize() — jieba 分词 + 去停用词
# ============================================================
class TestTokenize:
    """验证 jieba 分词正确过滤无意义高频词和标点。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modeling.job_clustering import tokenize as _tok
        self.tok = _tok

    def test_removes_stopwords(self):
        words = self.tok('Python工程师开发')
        # 'python' and '工程师' and '开发' are stopwords
        assert 'python' not in words
        assert '工程师' not in words
        assert '开发' not in words

    def test_keeps_meaningful(self):
        words = self.tok('高级Java后端')
        # "java" and "后端" and "高级" may be meaningful depending on stopword list
        assert len(words) > 0

    def test_empty_input(self):
        assert self.tok('') == []

    def test_punct_removed(self):
        """纯标点应全部被过滤。"""
        words = self.tok('()/（）、')
        assert words == []

    def test_lowercase_applied(self):
        """Python → python, 然后被停用词过滤。"""
        words = self.tok('Python')
        assert 'python' not in words

    def test_space_handling(self):
        words = self.tok('  测试   ')
        assert '测试' in words


# ============================================================
# _fuzzy_match() — 模糊匹配
# ============================================================
class TestFuzzyMatch:
    """验证模糊匹配/回退逻辑。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modeling.salary_predict import _fuzzy_match as _fm
        self.fm = _fm

    def test_exact_match_no_sub(self):
        val, sub = self.fm('本科', ['本科', '大专', '硕士'], '不限')
        assert val == '本科'
        assert sub is False

    def test_empty_returns_fallback(self):
        val, sub = self.fm('', ['本科', '大专'], '不限')
        assert val == '不限'
        assert sub is False

    def test_none_returns_fallback(self):
        val, sub = self.fm(None, ['本科'], '不限')
        assert val == '不限'
        assert sub is False

    def test_fuzzy_substring_match(self):
        """_fuzzy_match 逻辑是 value in v (输入是有效值的子串?), 不是 v in value。
        '大学本科' 不是任何有效值的子串,应回退到 fallback。"""
        val, sub = self.fm('大学本科', ['本科', '大专', '硕士'], '不限')
        assert val == '不限'
        assert sub is True

    def test_fuzzy_match_reverse(self):
        """当输入'本科'直接匹配时,不发生替换。"""
        val, sub = self.fm('本科', ['本科', '大专'], '不限')
        assert val == '本科'
        assert sub is False

    def test_complete_mismatch_fallback(self):
        val, sub = self.fm('博士', ['本科', '大专', '硕士'], '不限')
        assert val == '不限'
        assert sub is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
