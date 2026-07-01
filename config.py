"""
项目配置。从模块旁的 .env 文件读取密钥,不存在则降级到环境变量,
最后提供 DB_PATH / DB_URI / DEEPSEEK_API_KEY 三个常量供其它模块使用。
"""
import os


def _load_env_file():
    """解析 .env 文件(KEY=VALUE 格式,# 开头或空行忽略),并把键值写进 os.environ。
    已经在宿主系统里 export 过的同名变量会被保留,不会被覆盖。
    """
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.isfile(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            # 只去除首尾各一对匹配的引号(双引号或单引号),避免误删字面内容
            value = value.strip()
            if len(value) >= 2:
                if (value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'"):
                    value = value[1:-1]
            if key and value:
                os.environ.setdefault(key, value)


_load_env_file()


# SQLite 数据库文件路径(放在本模块所在目录)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')

# 便于需要 URI 格式的库使用
DB_URI = 'sqlite:///' + DB_PATH

# DeepSeek API Key,供 agent 使用;若未配置则为空字符串
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')

# 采集口令: 若配置了非空值,则 /collect 路由要求 POST 表单中带 token 字段匹配,
# 用于防止演示/教学场景下被人误点清空数据。不配置则不限制采集。
COLLECT_TOKEN = os.environ.get('COLLECT_TOKEN', '')
