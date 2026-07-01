"""
Flask 路由行为的单元测试（安全相关）。

使用 Flask test_client 发送请求，不启动真实服务器、不依赖真实浏览器。
依赖数据库存在即可（表不存在时路由也不应 500）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ---------- 测试夹具: Flask test client ----------
@pytest.fixture
def client():
    """构造 Flask 应用测试客户端。数据库空也没关系,路由不该 500。"""
    from app import app
    app.config['TESTING'] = True
    # CSRF 在测试态下临时关闭,单独测 CSRF 时再开启
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


# ============================================================
# L-1: /list 路由的 page 参数异常输入保护
# ============================================================
class TestListPageParamSafety:
    """验证 /list 的 page 参数在非法输入下返回 200 而非 500。"""

    def test_page_param_non_numeric_string_returns_200(self, client):
        """手动改 URL 传 ?page=abc 不能 ValueError 500。"""
        resp = client.get('/list?page=abc')
        assert resp.status_code == 200, (
            f"非数字 page 导致 {resp.status_code},预期 200 (应降级到第一页)"
        )

    def test_page_param_empty_returns_200(self, client):
        """?page= (空字符串) 返回 200。"""
        resp = client.get('/list?page=')
        assert resp.status_code == 200

    def test_page_param_negative_clamped_to_page_1(self, client):
        """?page=-99 返回 200 (页码应 clamp 到 1)。"""
        resp = client.get('/list?page=-99')
        assert resp.status_code == 200

    def test_page_param_zero_returns_200(self, client):
        """?page=0 返回 200,而不是 OFFSET 变成负数。"""
        resp = client.get('/list?page=0')
        assert resp.status_code == 200

    def test_page_param_float_returns_200(self, client):
        """?page=1.5 返回 200 (按 int 失败时默认第一页)。"""
        resp = client.get('/list?page=1.5')
        assert resp.status_code == 200

    def test_page_param_normal_number_ok(self, client):
        """合法 ?page=1 也得是 200 (保证改代码没破坏正常路径)。"""
        resp = client.get('/list?page=1')
        assert resp.status_code == 200


# ============================================================
# H-3+H-4: secret_key 存在性 + CSRF 保护生效
# ============================================================
class TestAppSecretAndCSRF:
    """验证 app.secret_key 被正确设置,以及 CSRF 保护生效。"""

    def test_app_has_non_empty_secret_key(self):
        """app.secret_key 不能为 None / 空字符串 (否则 session / CSRF 失效)。"""
        from app import app
        key = app.secret_key
        assert key is not None, "app.secret_key 未设置 (应为 Flask-WTF CSRF / session 前提)"
        assert len(key) > 0, "app.secret_key 为空字符串"

    def test_csrf_blocks_post_predict_without_token(self):
        """POST /predict 不带 CSRF token 返回 4xx (WTF_CSRF_CHECK_DEFAULT 生效)。"""
        from app import app
        # 注意: 这个测试里不关闭 CSRF,所以单独构造 app context
        csrf_app = app
        csrf_app.config['TESTING'] = False
        csrf_app.config['WTF_CSRF_ENABLED'] = True
        with csrf_app.test_client() as c:
            resp = c.post('/predict', data={
                'city': '北京', 'category': '后端开发',
                'edu': '本科', 'exper': '1-3年',
            })
            # Flask-WTF CSRF 失败默认是 400
            assert resp.status_code in (400, 403), (
                f"未带 CSRF token 的 POST /predict 返回 {resp.status_code},"
                f"预期 400/403 (CSRF 保护应该生效)"
            )


# ============================================================
# H-1: debug/host 不从硬编码读取,而从环境变量读取
# ============================================================
class TestDebugHostFromEnv:
    """验证 Flask 启动配置从环境变量读取,而不是硬编码 debug=True host=0.0.0.0。"""

    def test_debug_flag_defaults_off(self, monkeypatch):
        """没设 FLASK_DEBUG 时,debug 应该是 False (生产安全默认)。"""
        # 删掉环境变量里的 FLASK_DEBUG,模拟干净环境
        monkeypatch.delenv('FLASK_DEBUG', raising=False)
        monkeypatch.delenv('FLASK_HOST', raising=False)

        # 因为 app 模块可能已经被 import 过,我们直接读 app.config 里的相关设定
        # 更直接: 检查 app.py 中的启动逻辑是否依赖硬编码 debug=True
        import inspect
        import app as app_module
        source = inspect.getsource(app_module)
        # 启动语句里不能出现裸 debug=True (必须是环境变量驱动)
        hardcoded_debug_true = any(
            line.strip().startswith('app.run(') and 'debug=True' in line
            and 'os.environ' not in line and 'getenv' not in line
            for line in source.splitlines()
        )
        assert not hardcoded_debug_true, (
            "app.run() 中硬编码 debug=True。必须由 FLASK_DEBUG 环境变量控制,"
            "默认关闭。"
        )

    def test_host_not_wildcard_by_default(self, monkeypatch):
        """默认 host 不能是 0.0.0.0 (默认只有本机能访问)。"""
        import inspect
        import app as app_module
        source = inspect.getsource(app_module)
        # 查找 app.run 行,硬编码 host='0.0.0.0' 且无环境变量判断 = fail
        hardcoded_wildcard = any(
            line.strip().startswith('app.run(')
            and "'0.0.0.0'" in line and 'os.environ' not in line and 'getenv' not in line
            for line in source.splitlines()
        )
        assert not hardcoded_wildcard, (
            "app.run() 中硬编码 host='0.0.0.0'。默认必须是 127.0.0.1,"
            "通过 FLASK_HOST 环境变量显式开启对外监听。"
        )
