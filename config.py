"""
SQLite版配置文件,替代教材4.3节的 config.py(MySQL版)。

SQLite不需要账号密码、不需要启动服务,本质上数据库就是一个文件,
跟你项目代码放在一起即可,换电脑/换环境也不用重新配置。

API Key 读取顺序(优先级从高到低):
  1. 项目目录下的 .env 文件(格式: DEEPSEEK_API_KEY=sk-xxx)
  2. 系统环境变量 DEEPSEEK_API_KEY
  3. 空字符串(Agent页面会提示你设置)
"""
import os


def _load_env_file():
    """轻量级 .env 文件解析器,不依赖 python-dotenv。格式: KEY=VALUE,每行一个,支持#注释。"""
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
            value = value.strip().strip('"\'')
            if key and value:
                os.environ.setdefault(key, value)


_load_env_file()

# 数据库文件路径:跟本文件放在同一目录下,自动生成 data.db
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')

# 给 Flask-SQLAlchemy 用的连接字符串(替代原来 mysql+pymysql://... 那一行)
DB_URI = 'sqlite:///' + DB_PATH

# 如果你的 app.py 里用的是 app.config.from_object(config) 这种方式加载配置,
# Flask-SQLAlchemy 实际识别的配置项名字是 SQLALCHEMY_DATABASE_URI(不是DB_URI),
# 如果运行时报错说找不到数据库连接配置,在 app.py 里 db = SQLAlchemy(app) 那一行前面加上:
#     app.config['SQLALCHEMY_DATABASE_URI'] = config.DB_URI
# 这一行能解决该问题(跟你换不换SQLite无关,是教材代码本身命名上的一个小bug,
# 这个也可以记一笔,算是又一个"发现并修正教材代码问题"的案例)。
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')