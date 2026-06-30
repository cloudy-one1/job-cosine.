"""
这不是一个独立运行的文件,是要粘贴进你现有 app.py 里的代码片段。

具体步骤:
1. 在 app.py 顶部,跟其他 import 放一起,加上:
       from agent_core import run_agent

2. 在文件末尾、if __name__ == '__main__': 之前,加上下面这个路由函数

3. 确认 config.py 里已经有 DEEPSEEK_API_KEY 这一行
"""

# ==================== 把下面这段加进 app.py ====================

@app.route('/advice', methods=['GET', 'POST'])
def advice():
    """求职建议Agent页面"""
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

# ================================================================
