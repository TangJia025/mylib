#!/usr/bin/env python3
"""
v3_subagent.py - Mini Claude Code: 子代理机制 (~450 行代码)

核心理念："分而治之，上下文隔离"
=============================================================
v2 添加了规划。但对于像"探索代码库然后重构 auth"这样的大型任务，
单个代理会遇到问题：

问题 - 上下文污染:
-------------------------------
    单代理历史:
      [探索中...] cat file1.py -> 500 lines
      [探索中...] cat file2.py -> 300 lines
      ... 还有 15 个文件 ...
      [现在重构...] "等等，file1 包含什么？"

模型的上下文充满了探索细节，留给实际任务的空间很小。
这就是"上下文污染"。

解决方案 - 具有隔离上下文的子代理:
----------------------------------------------
    主代理历史:
      [任务: 探索代码库]
        -> 子代理探索 20 个文件 (在自己的上下文中)
        -> 仅返回: "Auth in src/auth/, DB in src/models/"
      [现在在干净的上下文中重构]

每个子代理都有:
  1. 自己新鲜的消息历史
  2. 过滤后的工具 (探索代理不能写入)
  3. 专门的系统提示词
  4. 仅向父代理返回最终总结

关键见解:
---------------
    进程隔离 = 上下文隔离

通过生成子任务，我们获得:
  - 主代理的干净上下文
  - 并行探索成为可能
  - 自然的任务分解
  - 相同的代理循环，不同的上下文

代理类型注册表:
-------------------
    | 类型    | 工具                | 目的                        |
    |---------|---------------------|---------------------------- |
    | explore | bash, read_file     | 只读探索                    |
    | code    | all tools           | 完全实现访问权限            |
    | plan    | bash, read_file     | 设计而不修改                |

典型流程:
-------------
    用户: "重构 auth 以使用 JWT"

    主代理:
      1. Task(explore): "查找所有与 auth 相关的文件"
         -> 子代理读取 10 个文件
         -> 返回: "Auth in src/auth/login.py..."

      2. Task(plan): "设计 JWT 迁移"
         -> 子代理分析结构
         -> 返回: "1. Add jwt lib 2. Create utils..."

      3. Task(code): "实现 JWT 令牌"
         -> 子代理编写代码
         -> 返回: "Created jwt_utils.py, updated login.py"

      4. 向用户总结变更

用法:
    python v3_subagent.py

样例：统计当前目录下的代码行数和功能，详细分析每个文件的执行流程，包括调用的函数和类，输出到 html 中
"""

import sys
import time
import traceback
from pathlib import Path
from llm_factory import LLMFactory, LLMChatAdapter
from util.mylog import logger
from utils import execute_base_tools, TodoManager, get_agent_descriptions, BASE_TOOLS, SUBAGENT_ALL_TOOLS, AGENT_TYPES

# 初始化 API 客户端
# 使用 LLMFactory 创建 LLM 实例
llm = LLMFactory.create(
    model_type="openai",
    model_name="deepseek-v3.1", # 使用支持的模型
    temperature=0.0,
    max_tokens=8192
)
client = LLMChatAdapter(llm)
WORKDIR = Path.cwd()

TODO = TodoManager()

SYSTEM = f"""你是一个位于 {WORKDIR} 的编码代理，系统为 {sys.platform}。

## 执行流程
计划（使用 TodoWrite）-> 使用工具行动 -> 执行子代理工具 -> 报告。

你可以为复杂的子任务生成子代理：
{get_agent_descriptions()}

## 规则
- 对需要集中探索或实现的子任务使用 Task 工具
- 使用 TodoWrite 跟踪多步骤工作
- 优先使用工具而不是文字描述。先行动，不要只是解释。
- 完成后，总结变更内容。"""

max_steps = 20

def get_tools_for_agent(agent_type: str) -> list:
    allowed = AGENT_TYPES.get(agent_type, {}).get("tools", "*")

    if allowed == "*":
        return BASE_TOOLS  # All base tools, but NOT Task (no recursion in demo)

    return [t for t in BASE_TOOLS if t["name"] in allowed]

def run_task(description: str, prompt: str, agent_type: str, max_steps: int = max_steps) -> str:
    """
    在隔离的上下文中执行子代理任务。

    这是子代理机制的核心：

    1. 创建隔离的消息历史（关键：没有父级上下文！）
    2. 使用特定于代理的系统提示词
    3. 根据代理类型过滤可用工具
    4. 运行与主代理相同的查询循环
    5. 仅返回最终文本（不是中间细节）

    父代理只看到总结，保持其上下文干净。

    进度显示：
    ----------------
    运行时，我们会显示：
      [explore] find auth files ... 5 tools, 3.2s

    这在不污染主对话的情况下提供了可见性。
    """
    if agent_type not in AGENT_TYPES:
        return f"Error: Unknown agent type '{agent_type}'"

    config = AGENT_TYPES[agent_type]

    sub_system = f"""你是一个位于 {WORKDIR} 的 {agent_type} 子代理，系统为 {sys.platform}。

{config["prompt"]}

完成任务并返回清晰、简洁的总结。"""

    sub_tools = get_tools_for_agent(agent_type)
    sub_messages = [{"role": "system", "content": sub_system}, {"role": "user", "content": prompt}]

    logger.info(f"      [子代理][{agent_type}] {description}")
    start = time.time()
    tool_count = 0

    step = 0
    while step < max_steps:
        step += 1
        response = client.chat_with_tools(
            prompt='',
            messages=sub_messages,
            tools=sub_tools,
        )

        assistant_text = []
        tool_calls = []

        for block in response.content:
            if hasattr(block, "text"):
                assistant_text.append(block.text)
                logger.info(f"      [子代理][{agent_type}] {block.text}")
            if block.type == "tool_use":
                tool_calls.append(block)

        full_text = "\n".join(assistant_text)
        if not tool_calls:
            logger.info(f"      [子代理][{agent_type}] 第 {step} 步结束，无工具调用")
            break

        results = []

        for tc in tool_calls:
            tool_count += 1
            output = execute_tool(tc.name, tc.input)
            results.append(f"      [子代理][{agent_type}] 工具 {tc.name}, 输入: {tc.input}, 返回: {output}")
            elapsed = time.time() - start
            sys.stdout.write(
                f"\r      [子代理][{agent_type}] {description} ... {tool_count} tools, {elapsed:.1f}s\n"
            )
            sys.stdout.flush()

        sub_messages.append({"role": "assistant", "content": full_text})
        combined_output = "\n".join(results)
        sub_messages.append({"role": "user", "content": f"子代理执行结果：\n{combined_output}\n\n请继续处理"})

    elapsed = time.time() - start
    sys.stdout.write(
        f"\r      [子代理][{agent_type}] {description} - done ({tool_count} tools, {elapsed:.1f}s)\n"
    )

    for block in response.content:
        if hasattr(block, "text"):
            return full_text

    return "(subagent returned no text)"

def execute_tool(name: str, args: dict) -> str:
    result = execute_base_tools(name, args)
    if result is not None:
        return result

    if name == "TodoWrite":
        try:
            return TODO.update(args["items"])
        except Exception as e:
            return f"Error: {e}"

    if name == "Task":
        return run_task(args["description"], args["prompt"], args["agent_type"])

    return f"Unknown tool: {name}"

def agent_loop(prompt: str, history: list, max_steps: int = max_steps) -> list:
    # 检查历史记录中是否已有系统提示词（作为系统消息）
    has_system = any(msg.get("role") == "system" for msg in history)
    if not has_system:
        # 在开头添加系统提示词作为系统消息
        history.insert(0, {"role": "system", "content": SYSTEM})

    step = 0
    while step < max_steps:
        step += 1
        response = client.chat_with_tools(
            prompt=prompt,
            messages=history,
            tools=SUBAGENT_ALL_TOOLS,
        )

        assistant_text = []
        tool_calls = []

        for block in response.content:
            if hasattr(block, "text"):
                assistant_text.append(block.text)
                logger.info(block.text)
            if block.type == "tool_use":
                tool_calls.append(block)

        full_text = "\n".join(assistant_text)
        if not tool_calls:
            history.append({"role": "assistant", "content": full_text})
            logger.info(f"第 {step} 步结束，无工具调用")
            return history

        results = []
        for tc in tool_calls:
            if tc.name == "Task":
                logger.info(f"\n> [使用工具] Task 第 {step} 步调用: {tc.input.get('description', 'subtask')}")
            else:
                logger.info(f"\n> [使用工具] {tc.name} 第 {step} 步调用: {tc.input}")

            logger.info(f"  输入: {tc.input}")
            output = execute_tool(tc.name, tc.input)
            if tc.name != "Task":
                preview = output[:200] + "..." if len(output) > 200 else output
                logger.info(f"  [使用工具] {tc.name}, 返回: {preview}")
                
            results.append(f"工具 {tc.name}, 输入: {tc.input}, 返回: {output}")

        history.append({"role": "assistant", "content": full_text})
        combined_output = "\n".join(results)
        history.append({"role": "user", "content": f"执行结果：\n{combined_output}\n\n请继续处理"})

def main():
    logger.info(f"Mini Claude Code v3 (with Subagents) - {WORKDIR}")
    logger.info(f"Agent types: {', '.join(AGENT_TYPES.keys())}")
    logger.info("Type 'exit' to quit.\n")

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("exit", "quit", "q"):
            break

        history.append({"role": "user", "content": user_input})

        try:
            agent_loop('', history, max_steps=max_steps)
        except Exception as e:
            logger.error(f"Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()