"""
薪资解析单元测试 — 覆盖 parse_salary() 所有分支。

涵盖：面议、万/月、千/月、万/年、缺单位继承、日薪、边缘输入。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from data.salary_parser import parse_salary


class TestNegotiableAndEmpty:
    """面议、空值、None 输入。"""

    def test_mianyi_returns_zero(self):
        assert parse_salary('面议') == (0.0, 0.0)

    def test_empty_string_returns_zero(self):
        assert parse_salary('') == (0.0, 0.0)

    def test_none_returns_zero(self):
        assert parse_salary(None) == (0.0, 0.0)

    def test_mianyi_with_prefix(self):
        assert parse_salary('薪资面议') == (0.0, 0.0)


class TestWanPerMonth:
    """万/月 格式 — 最常见的51job格式。"""

    def test_simple_range_wan(self):
        vmin, vmax = parse_salary('1.5-2万/月')
        assert vmin == 15.0  # 1.5万 = 15k
        assert vmax == 20.0  # 2万 = 20k

    def test_only_max_has_unit_backward_inherit(self):
        """关键测试: "1.5-2万" 中 1.5 缺单位,应继承后面 2 的 "万" 单位。"""
        vmin, vmax = parse_salary('1.5-2万')
        assert vmin == 15.0
        assert vmax == 20.0

    def test_integer_range_wan(self):
        vmin, vmax = parse_salary('2-3万/月')
        assert vmin == 20.0
        assert vmax == 30.0

    def test_single_value_wan(self):
        vmin, vmax = parse_salary('1万以上/月')
        assert vmin == 10.0
        assert vmax == 10.0


class TestQianPerMonth:
    """千/月 格式。"""

    def test_simple_range_qian(self):
        vmin, vmax = parse_salary('8千-1.2万/月')
        # "8千"=8k, "1.2万"=12k
        assert vmin == 8.0
        assert vmax == 12.0

    def test_both_qian(self):
        vmin, vmax = parse_salary('3千-4.5千/月')
        assert vmin == 3.0
        assert vmax == 4.5

    def test_mixed_unit_qian_to_qian(self):
        """向后继承: "3-4.5千" → 3继承4.5的"千"单位。"""
        vmin, vmax = parse_salary('3-4.5千/月')
        assert vmin == 3.0
        assert vmax == 4.5


class TestYearlySalary:
    """年薪 → 月薪换算。"""

    def test_wan_per_year_to_month(self):
        vmin, vmax = parse_salary('15-25万/年')
        # 15万/12 = 12.5k/月, 25万/12 ≈ 20.83k/月
        assert vmin == 12.5
        assert vmax == pytest.approx(20.83, rel=1e-2)

    def test_single_year(self):
        vmin, vmax = parse_salary('10万/年')
        assert vmin == pytest.approx(8.33, rel=1e-2)
        assert vmax == pytest.approx(8.33, rel=1e-2)


class TestDayRate:
    """日薪 → 月薪换算 (21.75天/月 / 1000转千元)。"""

    def test_day_rate(self):
        vmin, vmax = parse_salary('300-500/天')
        # 300*21.75/1000 ≈ 6.53, 500*21.75/1000 ≈ 10.88
        assert vmin == pytest.approx(6.52, rel=0.01)
        assert vmax == pytest.approx(10.88, rel=0.01)

    def test_single_day_rate(self):
        vmin, vmax = parse_salary('200/天')
        assert vmin == pytest.approx(4.35, rel=0.01)
        assert vmax == pytest.approx(4.35, rel=0.01)


class TestBonusSeparation:
    """·13薪 等分隔符处理。"""

    def test_bonus_stripped(self):
        vmin, vmax = parse_salary('1.3-1.5万·13薪')
        assert vmin == 13.0
        assert vmax == 15.0

    def test_bonus_stripped_2(self):
        vmin, vmax = parse_salary('2-3万·14薪')
        assert vmin == 20.0
        assert vmax == 30.0


class TestEdgeInputs:
    """边缘/异常输入。"""

    def test_no_number(self):
        assert parse_salary('薪资待遇优厚') == (0.0, 0.0)

    def test_whitespace_only(self):
        assert parse_salary('   ') == (0.0, 0.0)

    def test_large_number(self):
        vmin, vmax = parse_salary('50-80万/年')
        assert vmin == pytest.approx(41.67, rel=0.01)
        assert vmax == pytest.approx(66.67, rel=0.01)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
