"""
模型缓存 — 整个应用唯一的模型真相来源。

app.py 启动/重采集后更新;
agent_tools 和 app.py 的路由共享同一份引用,消除重复训练和全局变量不一致。
"""
_model_result = None


def get():
    """返回当前缓存的模型结果;如尚未训练(直接运行工具模块的场景),按需训练。"""
    global _model_result
    if _model_result is None:
        from modeling.salary_predict import train_and_evaluate
        _model_result = train_and_evaluate()
    return _model_result


def update(result):
    """用外部训练好的结果更新缓存。"""
    global _model_result
    _model_result = result
