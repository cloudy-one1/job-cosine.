"""
data 表的数据清洗工具。

有时导入的行会包含冗余的城市前缀,例如:

    "广州-广州·天河区" -> "广州-天河区"
    "广州-广州"        -> "广州"

运行此脚本会就地修复这些行。

用法: python -m data.fix_duplicate_address
      或: python data/fix_duplicate_address.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import config


def clean_address(addr):
    if not addr or '-' not in addr:
        return addr
    city, rest = addr.split('-', 1)
    if rest == city:
        return city
    if rest.startswith(city + '·'):
        district = rest[len(city) + 1:]
        return city + '-' + district
    return city + '-' + rest.replace('·', '-')


def main():
    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()
    cursor.execute("SELECT id, address FROM data")
    rows = cursor.fetchall()

    changed = 0
    for rid, addr in rows:
        fixed = clean_address(addr)
        if fixed != addr:
            cursor.execute("UPDATE data SET address = ? WHERE id = ?", (fixed, rid))
            changed += 1

    db.commit()
    db.close()
    print(f'共检查 {len(rows)} 条,修复了 {changed} 条重复城市名的地址')


if __name__ == '__main__':
    main()
