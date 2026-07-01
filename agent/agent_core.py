"""
手写实现的 ReAct (Reason + Act) agent 循环,未使用任何框架,
目的是让每一步的输出都能在 trace 中清晰看到。

核心流程:
  1. 让大模型从两种结构化输出中选择一种:
       - Thought + Action + Action Input  (需要调用工具)
       - Thought + Final Answer           (信息足够,给出最终答案)
  2. 解析工具调用,执行对应的 Python 函数,把返回值包装为 Observation,
     连同完整对话历史再喂给大模型。
  3. 当大模型输出 Final Answer 或到达 max_steps(防止死循环)时终止。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
import time
import inspect
import requests

from agent.agent_tools import TOOLS

DEEPSEEK_API_URL = 'https://api.deepseek.com/chat/completions'

SYSTEM_PROMPT_TEMPLATE = """You are a job-market assistant. Answer the user's question
by querying a local SQLite database of job postings. Do not invent numbers or statistics
that were not returned by a tool.

Available tools:
{tool_list}

Respond in one of two formats.

Format 1 -- you need to call a tool first:
Thought: one sentence describing what information you need and why
Action: exactly one of the tool names listed above
Action Input: {{"parameter_name": "parameter_value"}}  (use {{}} for parameterless tools)

Format 2 -- you already have enough information to answer:
Thought: one sentence describing what the tools returned
Final Answer: a natural-language answer that cites specific numbers from the tool results

Important: emit only ONE format per turn. Wait until you receive the Observation
before issuing a Final Answer."""


def build_system_prompt():
    tool_lines = []
    for name, info in TOOLS.items():
        tool_lines.append(f"- {name}: {info['description']}")
    return SYSTEM_PROMPT_TEMPLATE.format(tool_list='\n'.join(tool_lines))


def call_deepseek(messages, api_key, model='deepseek-chat', max_retries=3):
    """调用 DeepSeek API,带指数退避重试,应对网络抖动。"""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={'model': model, 'messages': messages, 'temperature': 0.3},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()['choices'][0]['message']['content']
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s, 8s
                print(f'[Agent] API 调用失败(第{attempt}次),{wait}s后重试: {e}')
                time.sleep(wait)
    raise last_error


def parse_llm_output(text):
    """判断大模型输出是工具调用还是最终答案。"""
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
    """执行完整的 ReAct 循环,返回 (final_answer, trace) 元组。

    llm_call 是可选钩子,用来替换真实的 DeepSeek HTTP 调用(测试时使用,避免消耗额度)。
    trace 是按轮记录的列表(thought / action / observation),方便在 advice 页面展示推理过程。
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
            print(f'--- 第 {step} 轮大模型输出 ---\n{reply}\n')

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
                    # 白名单过滤: 只传入函数签名中实际接受的参数。
                    # LLM 可能产生幻觉参数或多余字段,直接 ** 解包会 TypeError。
                    sig = inspect.signature(func)
                    valid_params = set(sig.parameters.keys())
                    filtered_input = {k: v for k, v in tool_input.items() if k in valid_params}
                    result = func(**filtered_input)
                except Exception as e:
                    result = f'Tool call failed: {e}'
            else:
                result = f'No tool named "{tool_name}". Available tools: {list(TOOLS.keys())}'
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
                'content': 'Observation: no valid Action or Final Answer detected. '
                            'Please re-emit using the exact format from the system prompt.'
            })

    fallback = '达到最大迭代轮数仍未得到结论,请尝试更具体的问题。'
    trace.append({'step': max_steps + 1, 'type': 'final', 'content': fallback})
    return fallback, trace


if __name__ == '__main__':
    import config
    api_key = getattr(config, 'DEEPSEEK_API_KEY', '')
    if not api_key:
        print('DEEPSEEK_API_KEY 未配置,请在 .env 文件或环境变量中设置。')
    else:
        question = input('请输入问题(例如: Python Web 开发岗位在本地区的就业形势如何?): ')
        answer, trace = run_agent(question, api_key)
        print('=== 最终答案 ===')
        print(answer)
