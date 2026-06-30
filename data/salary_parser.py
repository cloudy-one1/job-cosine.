"""
薪资字符串解析工具(独立模块)。

之前这个函数和"读取 CSV 并清空数据库重新导入"的 main()
写在同一个文件里,容易在不知情的情况下覆盖当前数据。
覆盖掉新采集的结果(实测踩到过这个问题)。现在把真正被其他模块复用的
parse_salary()单独拆出来,这个文件本身没有main()入口,不会被误跑。
"""
import re


def parse_salary(raw):
    """
    解析51job真实API返回的薪资字符串,返回(min, max),单位千元/月。
    常见格式: "1.5-2万/月" "8千-1.2万/月" "15-25万/年" "1.3-1.5万·13薪"
             "面议" "3千-4.5千/月" "1万以上/月"

    关键陷阱(实测踩到过,记录下来): 中文薪资简写里,单位经常只写在
    最后一个数字后面,比如"1.5-2万"实际表示"1.5万-2万",不是"1.5(不知道单位)-2万"。
    如果直接按"字符串里有没有'万'/'千'"整体判断,会把单位错误地套用到
    每一个数字上,导致"8千-1.2万"被错误解析成"80-12"(都按万算)。
    正确做法是:每个数字只认自己紧跟着的单位,缺单位的数字向后看,
    继承后面最近一个数字的单位。
    """
    if not raw or '面议' in raw:
        return 0.0, 0.0

    raw_clean = raw.split('·')[0]
    is_year = '/年' in raw_clean
    is_day = '/天' in raw_clean

    matches = [(num, unit) for num, unit in re.findall(r'(\d+\.?\d*)(万|千)?', raw_clean) if num]
    if not matches:
        return 0.0, 0.0

    if is_day:
        vmin = round(float(matches[0][0]) * 21.75 / 1000, 2)
        vmax = round(float(matches[-1][0]) * 21.75 / 1000, 2)
        return vmin, vmax

    # 缺单位的数字,向后继承最近一个数字的单位("1.5-2万" -> 1.5也按"万"算)
    filled = []
    last_unit = None
    for num, unit in reversed(matches):
        if unit:
            last_unit = unit
        filled.append((num, unit or last_unit))
    filled.reverse()

    def to_k(num_str, unit):
        v = float(num_str)
        return v * 10 if unit == '万' else v  # 千 或 无单位 都按原数值

    if len(filled) >= 2:
        vmin, vmax = to_k(*filled[0]), to_k(*filled[1])
    else:
        vmin = vmax = to_k(*filled[0])

    if is_year:
        vmin, vmax = round(vmin / 12, 2), round(vmax / 12, 2)

    return round(vmin, 2), round(vmax, 2)


if __name__ == '__main__':
    tests = ['1.5-2万/月', '8千-1.2万/月', '15-25万/年', '1.3-1.5万·13薪', '面议']
    for t in tests:
        print(f'{t!r:20} -> {parse_salary(t)}')
