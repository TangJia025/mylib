#!/usr/bin/env python3
"""
v0_bash.py - Mini Claude Code: Bash 是一切 (~50 行核心代码)
使用 LLMFactory 重新实现。

样例：统计当前目录下的代码行数，输出到控制台
"""

import sys
import os
import traceback

import pathlib

# 把脚本所在目录的父目录加入搜索路径
_script_dir = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir.parent))

from llm_factory import LLMFactory, LLMChatAdapter
from util.mylog import logger
from utils import run_bash, BASH_TOOLS

# 初始化 API 客户端
# 使用 LLMFactory 创建 LLM 实例
llm = LLMFactory.create(
    model_type="qwen",
    model_name="Bili-Qwen3-32B", # 使用支持的模型
    temperature=0.0,
    max_tokens=8192
)
client = LLMChatAdapter(llm)

# 系统提示词
SYSTEM = f"""你是一个位于 {os.getcwd()} 的 CLI 代理，系统为 {sys.platform}。使用 bash 命令解决问题。

## 规则：
- 优先使用工具而不是文字描述。先行动，后简要解释。
- 读取文件：cat, grep, find, rg, ls, head, tail
- 写入文件：echo '...' > file, sed -i, 或 cat << 'EOF' > file
- 避免危险操作，如 rm -rf等删除或者清理文件, 或格式化挂载点，或对系统文件进行写操作

## 要求
- 不使用其他工具，仅使用 bash 命令或者 shell 脚本
- 子代理可以通过生成 shell 代码执行
- 如果当前任务超过 bash 的处理范围，则终止不处理
"""

def extract_bash_commands(text):
    """从 LLM 响应中提取 bash 命令"""
    import re
    pattern = r'```bash\n(.*?)\n```'
    matches = re.findall(pattern, text, re.DOTALL)
    return [cmd.strip() for cmd in matches if cmd.strip()]

def chat(prompt, history=None, max_steps=10):
    """
    一个函数中包含完整的代理循环。
    """
    if history is None:
        history = []
    
    # 检查历史记录中是否已有系统提示词（作为系统消息）
    has_system = any(msg.get("role") == "system" for msg in history)
    if not has_system:
         # 在开头添加系统提示词作为系统消息
         history.insert(0, {"role": "system", "content": SYSTEM})
         logger.info(f"last item1: {history[-1]}, len: {len(history)}")

    history.append({"role": "user", "content": prompt})
    logger.info(f"last item2: {history[-1]}, len: {len(history)}")

    step = 0
    while step < max_steps:
        step += 1
        # 1. 调用模型（传递 tools 参数）
        # 使用 chat_with_tools 接口，支持 function calling
        response = client.chat_with_tools(
            prompt=prompt,
            messages=history,
            tools=BASH_TOOLS
        )
        if step == 1:
            prompt = '继续'

        # 2. 解析响应内容
        assistant_text = []
        tool_calls = []
        
        logger.info(f"第 {step} 步响应: {response}")

        # chat_with_tools 返回的是 Response 对象，包含 content 列表
        for block in response.content:
            if getattr(block, "type", "") == "text":
                logger.info("111 返回了文本")
                assistant_text.append(block.text)
            elif getattr(block, "type", "") == "tool_use":
                logger.info("222 返回了工具调用")
                tool_calls.append(block)

        # 记录助手文本回复
        full_text = "\n".join(assistant_text)
        if full_text:
            logger.info(f"助手: {full_text}")
            history.append({"role": "assistant", "content": full_text})
            logger.info(f"last item3: {history[-1]}, len: {len(history)}")
        elif tool_calls:
            # 如果只有工具调用没有文本，添加一个占位文本到历史，保持对话连贯
            logger.info(f"工具lll")
            history.append({"role": "assistant", "content": "(Executing tools...)"})
            logger.info(f"last item4: {history[-1]}, len: {len(history)}")
        
        # 3. 如果没有工具调用，直接返回内容
        if not tool_calls:
            logger.info(f"第 {step} 步结束，无工具调用")
            if response.stop_reason == "end_turn":
                return full_text
            # 如果异常结束，也返回
            return full_text or "(No response)"

        # 4. 执行工具
        logger.info(f"第 {step} 步工具调用: {tool_calls}")
        all_outputs = []
        for tc in tool_calls:
            if tc.name == "bash":
                cmd = tc.input.get("command")
                if cmd:
                    logger.info(f"[使用工具] {cmd}")  # 黄色显示命令
                    output = run_bash(cmd)
                    all_outputs.append(f"$ {cmd}\n{output}")
                    # 如果输出太长则截断打印
                    if len(output) > 200:
                        logger.info(f"输出: {output[:200]}... (已截断)")
                    else:
                        logger.info(f"输出: {output}")
            else:
                logger.warning(f"Unknown tool: {tc.name}")
        
        # 5. 将命令执行结果添加到历史记录中
        if all_outputs:
            combined_output = "\n".join(all_outputs)
            history.append({"role": "user", "content": f"执行结果：\n{combined_output}\n\n请继续处理。"})
            logger.info(f"last item5: {history[-1]}, len: {len(history)}")
        else:
            # 有工具调用但没产生输出（可能是解析失败或空命令）
            history.append({"role": "user", "content": "Error: Tool call failed or produced no output."})
            logger.info(f"last item6: {history[-1]}, len: {len(history)}")

    return "达到最大执行步数限制，停止执行。"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        logger.info(chat(sys.argv[1]))
    else:
        # 交互模式
        logger.info("Bash 代理已启动。输入 'exit' 退出。")
        history = []
        while True:
            try:
                user_input = input("> ")
                if user_input.lower() in ['exit', 'quit']:
                    break
                chat(user_input, history)
            except KeyboardInterrupt:
                logger.info("\n正在退出...")
                break
            except Exception as e:
                logger.info(f"\n错误: {e}")
                traceback.print_exc()
