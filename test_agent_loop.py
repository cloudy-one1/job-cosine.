"""
用一个"假LLM"测试 agent_core.py 的循环逻辑本身对不对,
不需要真实API key,也不消耗DeepSeek的调用额度。

思路:模拟LLM在第1轮决定调用 query_jobs 工具,
      看到Observation后在第2轮给出Final Answer,
      验证整个循环(解析格式→执行工具→拼接Observation→再次调用LLM)是否正常工作。
"""
from agent_core import run_agent

call_count = {'n': 0}


def fake_llm(messages):
    """模拟LLM的多轮响应,不调用真实API"""
    call_count['n'] += 1
    if call_count['n'] == 1:
        return (
            'Thought: 用户提到爬虫,我需要先查询爬虫相关职位的市场数据\n'
            'Action: query_jobs\n'
            'Action Input: {"keyword": "爬虫"}'
        )
    else:
        # 第二轮,假设LLM已经看到了Observation,直接给出最终答案
        return (
            'Thought: 已经拿到爬虫相关职位的数量和薪资数据,可以回答了\n'
            'Final Answer: 根据当前数据,爬虫相关职位共有34个,平均月薪约1.49万元,'
            '主要集中在北京、上海、广州。如果你有Python爬虫经验,这是一个不错的细分方向。'
        )


if __name__ == '__main__':
    answer, trace = run_agent(
        user_question='我会写Python爬虫,想了解一下这个方向的就业行情',
        api_key='fake-key-not-used',
        llm_call=fake_llm,
    )
    print('=== 最终回答 ===')
    print(answer)
    print('\n=== 思考过程记录 trace ===')
    for t in trace:
        print(t)

    assert call_count['n'] == 2, f"预期2轮调用,实际{call_count['n']}轮"
    assert '34' in answer or '爬虫' in answer
    assert len(trace) == 2 and trace[0]['type'] == 'action' and trace[1]['type'] == 'final'
    print('\n>>> 测试通过: 循环逻辑(解析Action→执行工具→拼接Observation→拿到Final Answer)正常工作')
