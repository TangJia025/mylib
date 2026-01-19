#!/usr/bin/env python3
"""
v1_basic.py - Mini Claude Code: 模型即代理 (~200 行代码)

核心理念："模型即代理"
=========================================
Claude Code, Cursor Agent, Codex CLI 的秘密是什么？其实没有秘密。

剥去 CLI 的光鲜外表、进度条、权限系统。剩下的部分出奇地简单：
一个让模型不断调用工具直到完成的循环。

传统助手：
    用户 -> 模型 -> 文本回复

代理系统：
    用户 -> 模型 -> [工具 -> 结果]* -> 回复
                          ^________|

这个星号 (*) 很关键！模型会反复调用工具，直到它认为任务已完成。
这通过将聊天机器人转变为自主代理。

关键洞察：模型是决策者。代码只是提供工具并运行循环。模型决定：
  - 调用哪些工具
  - 以什么顺序调用
  - 何时停止

四个基本工具：
------------------------
Claude Code 有约 20 个工具。但这 4 个涵盖了 90% 的用例：

    | 工具       | 用途                 | 示例                       |
    |------------|----------------------|----------------------------|
    | bash       | 运行任何命令         | npm install, git status    |
    | read_file  | 读取文件内容         | View src/index.ts          |
    | write_file | 创建/覆盖            | Create README.md           |
    | edit_file  | 精确修改             | Replace a function         |

仅凭这 4 个工具，模型可以：
  - 探索代码库 (bash: find, grep, ls)
  - 理解代码 (read_file)
  - 进行修改 (write_file, edit_file)
  - 运行任何东西 (bash: python, npm, make)
  
用法:
    python v1_basic.py

样例：统计当前目录下的代码行数，输出到 html 中
"""

from pathlib import Path
import sys
import traceback
from llm_factory import LLMFactory, LLMChatAdapter
from util.mylog import logger
from utils import execute_base_tools, BASIC_TOOLS

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

SYSTEM = f"""你是一个位于 {WORKDIR} 的编码代理，系统为 {sys.platform}。

## 执行流程
简要思考 -> 使用工具（使用 TOOLS） -> 报告结果。

## 规则
- 优先使用工具而不是文字描述。先行动，不要只是解释。  
- 永远不要臆造文件路径。如果不确定，先使用 bash ls/find 确认。  
- 做最小的修改。不要过度设计。  
- 完成后，总结变更内容。  

## 要求：
- 循环尽量简单，不要复杂。  
"""

def execute_tool(name: str, args: dict) -> str:
    """
    将工具调用分发给相应的实现。

    这是模型工具调用与实际执行之间的桥梁。
    每个工具返回一个字符串结果，该结果会反馈给模型。
    """
    result = execute_base_tools(name, args)
    if result is not None:
        return result
    return f"Unknown tool: {name}"

def agent_loop(prompt, history=None, max_steps=10) -> list:
    """
    在一个函数中包含完整的代理逻辑。

    这是所有编码代理共享的模式：

        while True:
            response = model(messages, tools)
            if no tool calls: return
            execute tools, append results, continue

    模型控制循环：
      - 持续调用工具直到 stop_reason != "tool_use"
      - 结果成为上下文（作为 "user" 消息反馈）
      - 记忆是自动的（messages 列表累积历史）

    为什么有效：
      1. 模型决定调用哪些工具、顺序以及何时停止
      2. 工具结果为下一个决策提供反馈
      3. 对话历史在多轮对话中保持上下文
    """

    if history is None:
        history = []
    
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
            tools=BASIC_TOOLS,
        )

        assistant_text = []
        tool_calls = []
        
        for block in response.content:
            if getattr(block, "type", "") == "text":
                assistant_text.append(block.text)
            elif getattr(block, "type", "") == "tool_use":
                tool_calls.append(block)
        
        full_text = "\n".join(assistant_text)
        if not tool_calls:
            history.append({"role": "assistant", "content": full_text})
            logger.info(f"第 {step} 步结束，无工具调用")
            return history

        results = []
        for tc in tool_calls:
            logger.info(f"\n> [使用工具] {tc.name} 第 {step} 步调用工具: {tc.input}")
            output = execute_tool(tc.name, tc.input)
            preview = output[:200] + "..." if len(output) > 200 else output
            logger.info(f"  [使用工具] {tc.name}, 输入: {tc.input}, 返回: {preview}")
            results.append(f"工具 {tc.name}, 输入: {tc.input}, 返回: {output}")

        history.append({"role": "assistant", "content": full_text})
        combined_output = "\n".join(results)
        history.append({"role": "user", "content": f"执行结果：\n{combined_output}\n\n请继续处理"})

    logger.info(f"第 {step} 步达到最大执行步数限制，停止执行。")

def main():
    """
    用于交互使用的简单读取-求值-打印循环 (REPL)。

    history 列表在轮次之间保持对话上下文，
    允许具有记忆的多轮对话。
    """
    logger.info(f"Mini Claude Code v1 - {WORKDIR}")
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
            agent_loop('', history, max_steps=10)
        except Exception as e:
            logger.error(f"Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()