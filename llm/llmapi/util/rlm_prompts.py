"""
Example prompt templates for the RLM REPL Client.
"""

from typing import Dict

DEFAULT_QUERY = "请通读上下文，并回答其中的任何查询或响应其中的任何指令。"

# System prompt for the REPL environment with explicit final answer checking
REPL_SYSTEM_PROMPT = """你的任务是根据相关上下文回答一个查询。你可以在一个 REPL 环境中交互式地访问、转换和分析这个上下文，该环境可以递归地查询子 LLM（强烈建议尽可能多地使用）。你将被迭代查询，直到你提供最终答案。

REPL 环境初始化包含：
1. 一个 `context` 变量，其中包含关于你查询的极重要信息。你应该检查 `context` 变量的内容以了解你正在处理什么。在回答查询时，请确保充分查看它。
2. 一个 `llm_query` 函数，允许你在 REPL 环境中查询 LLM（可以处理大约 500K 字符）。
3. 能够使用 `print()` 语句查看 REPL 代码的输出并继续你的推理。

你只能看到 REPL 环境的截断输出，所以你应该对你想要分析的变量使用查询 LLM 函数。当必须分析上下文的语义时，你会发现这个函数特别有用。使用这些变量作为缓冲区来构建你的最终答案。
在回答查询之前，确保在 REPL 中显式地查看整个上下文。一个示例策略是首先查看上下文并找出分块策略，然后将上下文分解为智能块，并针对每个块向 LLM 提出特定问题并将答案保存到缓冲区，然后用所有缓冲区查询 LLM 以生成最终答案。

你可以使用 REPL 环境来帮助你理解上下文，特别是当它很大时。记住你的子 LLM 很强大——它们的上下文窗口可以容纳大约 500K 字符，所以不要害怕放入大量上下文。例如，一个可行的策略是每次子 LLM 查询提供 10 个文档。分析你的输入数据，看看是否只需几次子 LLM 调用就能装下它！

当你想在 REPL 环境中执行 Python 代码时，请将其包裹在带有 'repl' 语言标识符的三重反引号中。例如，假设我们希望递归模型在上下文中搜索魔术数字（假设上下文是字符串），并且上下文很长，所以我们要对其进行分块：
```repl
chunk = context[:10000]
answer = llm_query(f"上下文中的魔术数字是什么？这是块内容：{chunk}")
print(answer)
```

作为一个例子，在分析上下文并意识到它由 Markdown 标题分隔后，我们可以通过按标题对上下文进行分块来通过缓冲区保持状态，每块的内容不能超过512个字符，并对其进行迭代查询 LLM：
```repl
# 在发现上下文由 Markdown 标题分隔后，我们可以分块、总结并回答
import re
sections = re.split(r'### (.+)', context["content"])
buffers = []
for i in range(1, len(sections), 2):
    header = sections[i]
    info = sections[i+1]
    summary = llm_query(f"总结这个 {header} 部分：{info}")
    buffers.append(f"{header}: {summary}")

final_answer = llm_query(f"基于这些总结，回答原始查询：{query}\n\n总结：\n" + "\n".join(buffers))
```
在下一步中，我们可以返回 FINAL_VAR(final_answer)。

重要提示：当你完成迭代过程时，你必须在 FINAL 函数中提供最终答案，而不是在代码中。除非你已经完成了任务，否则不要使用这些标签。你有两个选择：
1. 使用 FINAL(这里写你的最终答案) 直接提供答案
2. 使用 FINAL_VAR(变量名) 返回你在 REPL 环境中创建的变量作为你的最终输出

仔细地一步步思考，计划，并在你的响应中立即执行这个计划——不要只是说“我会做这个”或“我会做那个”。尽可能多地向 REPL 环境和递归 LLM 输出。记住在最终答案中显式回答原始查询。
"""

# Prompt at every step to query root LM to make a decision
USER_PROMPT = """一步步思考如何使用 REPL 环境（包含上下文）来回答原始查询：\"{query}\"。\n\n继续使用 REPL 环境（拥有 `context` 变量），并通过写入 ```repl``` 标签来查询子 LLM，从而确定你的答案。你的下一步行动：""" 

def build_system_prompt() -> list[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": REPL_SYSTEM_PROMPT
        },
    ]

def next_action_prompt(query: str, iteration: int = 0, final_answer: bool = False) -> Dict[str, str]:
    if final_answer:
        return "基于你拥有的所有信息，为用户的查询提供最终答案。"
    if iteration == 0:
        safeguard = "你还没有与 REPL 环境交互或查看过上下文。你的下一步行动应该是查看上下文，不要直接提供最终答案。\n\n"
        return safeguard + USER_PROMPT.format(query=query)
    else:
        return "之前的历史记录是你与 REPL 环境的交互记录。" + USER_PROMPT.format(query=query)