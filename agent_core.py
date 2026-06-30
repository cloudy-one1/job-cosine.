"""
Agent核心 —— 手写的"规划→调用工具→观察结果→再规划"循环(ReAct模式)。

不使用LangChain等框架,原因:那类框架会把这个循环完全封装隐藏起来,
你只需要调一个函数就能拿到结果,但你也因此说不清楚"循环内部到底发生了什么"。
这里手写出来,每一步在做什么、为什么这么设计,都可以直接对着代码讲清楚。

核心思路:
1. 把"可用工具列表"写进system prompt,要求LLM按固定格式输出
   (Thought/Action/Action Input 或者 Final Answer)
2. 解析LLM的输出文本,判断它是要"调用工具"还是"给出最终答案"
3. 如果是调用工具,就真正执行对应的Python函数,把结果当作"Observation"
   追加进对话历史,再让LLM看着这个结果继续思考
4. 循环直到拿到Final Answer,或者达到最大步数(防止死循环)

== 关于"防止死循环"这个设计 ==
这不是凭空加的保险——开发过程中实测过,如果不限制最大步数,
LLM有时会反复调用同一个工具或者陷入"Action格式输出错误→重试→又输出错误"
的循环,money不会自动停下来。这个问题本身就是一个值得写进周报的
真实AI协作纠错案例。
"""
import json
import re
import requests

from agent_tools import TOOLS

DEEPSEEK_API_URL = 'https://api.deepseek.com/chat/completions'

SYSTEM_PROMPT_TEMPLATE = """你是一个求职建议助手,通过调用工具查询本地招聘数据库来回答用户的问题。
你不能凭空编造数据,所有具体数字都必须来自工具返回的结果。

可用工具:
{tool_list}

请严格按以下格式之一输出,不要同时输出两种格式:

格式一(需要调用工具时):
Thought: 说明你现在的思考,判断需要查询什么信息
Action: 工具名(必须是上面列出的工具名之一)
Action Input: {{"参数名": "参数值"}}  (如果工具不需要参数,填 {{}})

格式二(已经有足够信息回答用户时):
Thought: 说明你已经掌握了哪些信息
Final Answer: 给用户的最终回答,要结合工具返回的具体数字,语气自然,不要罗列成报告

注意:每次只输出一轮 Thought+Action+Action Input,或者一轮 Thought+Final Answer,
等待工具返回结果(Observation)后再继续下一轮思考。"""


def build_system_prompt():
    tool_lines = []
    for name, info in TOOLS.items():
        tool_lines.append(f"- {name}: {info['description']}")
    return SYSTEM_PROMPT_TEMPLATE.format(tool_list='\n'.join(tool_lines))


def call_deepseek(messages, api_key, model='deepseek-chat'):
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={'model': model, 'messages': messages, 'temperature': 0.3},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def parse_llm_output(text):
    """解析LLM的输出,判断是Action还是Final Answer"""
    final_match = re.search(r'Final Answer:\s*(.*)', text, re.S)
    if final_match:
        return {'type': 'final', 'content': final_match.group(1).strip()}

    action_match = re.search(r'Action:\s*(\w+)', text)
    input_match = re.search(r'Action Input:\s*(\{.*?\})', text, re.S)
    if action_match:
        tool_name = action_match.group(1).strip()
        tool_input = {}
        if input_match:
            try:
                tool_input = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                tool_input = {}
        return {'type': 'action', 'tool': tool_name, 'input': tool_input}

    return {'type': 'unknown', 'raw': text}


def run_agent(user_question, api_key, max_steps=5, verbose=True, llm_call=None):
    """
    运行一次完整的Agent循环。
    llm_call 参数允许在测试时传入一个mock函数,替代真实的DeepSeek API调用
    (方便不消耗真实API额度的情况下测试循环逻辑本身)。

    返回 (final_answer: str, trace: list) —— trace记录了每一轮的
    思考/行动/观察,方便页面上把"AI协作过程"展示出来,不只是给一个结果。
    """
    if llm_call is None:
        llm_call = lambda messages: call_deepseek(messages, api_key)

    messages = [
        {'role': 'system', 'content': build_system_prompt()},
        {'role': 'user', 'content': user_question},
    ]
    trace = []

    for step in range(1, max_steps + 1):
        reply = llm_call(messages)
        if verbose:
            print(f'--- 第{step}轮 LLM输出 ---\n{reply}\n')

        parsed = parse_llm_output(reply)
        messages.append({'role': 'assistant', 'content': reply})

        if parsed['type'] == 'final':
            trace.append({'step': step, 'type': 'final', 'content': parsed['content']})
            return parsed['content'], trace

        if parsed['type'] == 'action':
            tool_name = parsed['tool']
            tool_input = parsed['input']
            if tool_name in TOOLS:
                func = TOOLS[tool_name]['func']
                try:
                    result = func(**tool_input)
                except Exception as e:
                    result = f'工具调用出错: {e}'
            else:
                result = f'不存在名为"{tool_name}"的工具,可用工具: {list(TOOLS.keys())}'
            observation = f'Observation: {result}'
            if verbose:
                print(f'{observation}\n')
            trace.append({
                'step': step, 'type': 'action', 'tool': tool_name,
                'input': tool_input, 'observation': str(result),
            })
            messages.append({'role': 'user', 'content': observation})
        else:
            trace.append({'step': step, 'type': 'unknown', 'raw': reply})
            messages.append({
                'role': 'user',
                'content': 'Observation: 没有识别到有效的Action或Final Answer,'
                            '请严格按照系统提示里的格式重新输出'
            })

    fallback = '已达到最大思考步数仍未得出结论,建议换一个更具体的问题再试。'
    trace.append({'step': max_steps + 1, 'type': 'final', 'content': fallback})
    return fallback, trace


if __name__ == '__main__':
    import config
    api_key = getattr(config, 'DEEPSEEK_API_KEY', '')
    if not api_key:
        print('请先在 config.py 里设置 DEEPSEEK_API_KEY')
    else:
        question = input('请输入你的问题(比如"我会Python爬虫,想了解一下行情"): ')
        answer, trace = run_agent(question, api_key)
        print('=== 最终回答 ===')
        print(answer)
