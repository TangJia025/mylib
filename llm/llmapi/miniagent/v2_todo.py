#!/usr/bin/env python3
"""
v2_todo.py - Mini Claude Code: 结构化规划 (~300 行代码)

核心理念："让计划可见"
=====================================
v1 对于简单任务很棒。但如果让它"重构 auth，添加测试，更新文档"，
看看会发生什么。如果没有明确的计划，模型会：
  - 随机地在任务之间跳转
  - 忘记已完成的步骤
  - 中途失去焦点

问题 - "上下文衰退":
----------------------------
在 v1 中，计划只存在于模型的"脑海"中：

    v1: "我会先做 A，然后 B，再做 C"  (不可见)
        10 次工具调用后: "等等，我在做什么？"

解决方案 - TodoWrite 工具:
-----------------------------
v2 添加了一个从根本上改变代理工作方式的新工具：

    v2:
      [ ] 重构 auth 模块
      [>] 添加单元测试         <- 当前正在进行
      [ ] 更新文档

现在你和模型都能看到计划。模型可以：
  - 在工作时更新状态
  - 看到已完成和待办事项
  - 专注于当前任务

关键约束（不是随意的 - 这些是护栏）:
------------------------------------------------------
    | 规则              | 原因                             |
    |-------------------|----------------------------------|
    | 最多 20 项        | 防止无限任务列表                 |
    | 一个进行中        | 强制专注于一件事                 |
    | 必填字段          | 确保结构化输出                   |

深刻见解:
----------------
> "结构既约束又赋能。"

Todo 约束（最大项目数，一个进行中）赋能（可见计划，进度跟踪）。

这种模式在代理设计中随处可见：
  - max_tokens 约束 -> 赋能可管理的响应
  - 工具模式约束 -> 赋能结构化调用
  - Todos 约束 -> 赋能复杂任务完成

好的约束不是限制，它们是脚手架。

用法:
    python v2_todo.py

样例：统计当前目录下的代码行数和功能，输出到 html 中
"""

import traceback
import sys
from pathlib import Path
from llm_factory import LLMFactory, LLMChatAdapter
from util.mylog import logger
from utils import execute_base_tools, TodoManager, BASE_TOOLS

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
计划（使用 TodoWrite） -> 使用工具行动（使用 TOOLS） -> 更新任务列表 -> 报告。

## 规则
- 使用 TodoWrite 跟踪多步骤任务
- 开始前将任务标记为 in_progress，完成后标记为 completed
- 优先使用工具而不是文字描述。先行动，不要只是解释。
- 完成后，总结变更内容。"""

# 在对话开始时显示
INITIAL_REMINDER = "<reminder>使用 TodoWrite 处理多步骤任务。</reminder>"

# 如果模型在一段时间内没有更新任务列表，则显示此提醒
NAG_REMINDER = "<reminder>超过 10 轮未更新任务列表。请更新任务列表。</reminder>"

max_steps = 20
rounds_without_todo = 0

def run_todo(items: list) -> str:
    try:
        return TODO.update(items)
    except Exception as e:
        return f"Error: {e}"

def execute_tool(name: str, args: dict) -> str:
    """Dispatch tool call to implementation."""
    result = execute_base_tools(name, args)
    if result is not None:
        return result

    if name == "TodoWrite":
        return run_todo(args["items"])

    return f"Unknown tool: {name}"

def agent_loop(prompt: str, history: list = [], max_steps: int = max_steps) -> list:
    global rounds_without_todo

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
            tools=BASE_TOOLS,
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
        used_todo = False

        for tc in tool_calls:
            logger.info(f"\n> [使用工具] {tc.name} 第 {step} 步调用: {tc.input}")
            output = execute_tool(tc.name, tc.input)
            preview = output[:200] + "..." if len(output) > 200 else output
            logger.info(f" [使用工具] {tc.name}, 输入: {tc.input}, 返回: {preview}")
            results.append(f"工具 {tc.name}, 输入: {tc.input}, 返回: {output}")
            if tc.name == "TodoWrite":
                used_todo = True

        if used_todo:
            rounds_without_todo = 0
        else:
            rounds_without_todo += 1

        history.append({"role": "assistant", "content": full_text})
        combined_output = "\n".join(results)
        history.append({"role": "user", "content": f"执行结果：\n{combined_output}\n\n请继续处理"})

def main():
    global rounds_without_todo

    logger.info(f"Mini Claude Code v2 (with Todos) - {WORKDIR}")
    logger.info("Type 'exit' to quit.\n")

    history = []
    first_message = True

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("exit", "quit", "q"):
            break

        content = []

        if first_message:
            content.append(INITIAL_REMINDER)
            first_message = False
        elif rounds_without_todo > max_steps:
            content.append(NAG_REMINDER)

        content.append(f"输入：{user_input}")
        history.append({"role": "user", "content": "\n".join(content)})

        try:
            agent_loop('', history, max_steps=max_steps)
        except Exception as e:
            logger.error(f"Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()