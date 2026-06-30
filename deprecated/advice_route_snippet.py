"""
大模型驱动的咨询页面路由参考。本文件记录 app 模块中注册在 /advice
下的 Flask 处理器,作为独立片段便于单独审阅和打补丁。

需要在 app 顶部添加:
    from agent_core import run_agent
同时 config.DEEPSEEK_API_KEY 必须已配置。
实际运行实现位于 app 模块中,本文件是只读参考副本。
"""

@app.route('/advice', methods=['GET', 'POST'])
def advice():
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if not question:
            return render_template('advice.html', error='请输入你的问题')
        try:
            answer, trace = run_agent(question, config.DEEPSEEK_API_KEY, max_steps=5, verbose=False)
        except Exception as e:
            return render_template('advice.html', error=f'Agent调用出错: {e}', question=question)
        return render_template('advice.html', question=question, answer=answer, trace=trace)
    return render_template('advice.html')
