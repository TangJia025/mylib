#!/usr/bin/env python3
"""
v4_skills.py - Mini Claude Code: 技能机制 (~550 行代码)

核心理念："知识外置"
============================================
v3 为我们提供了用于任务分解的子代理。但还有一个更深层的问题：

    模型如何知道**如何**处理特定领域的任务？

- 处理 PDF？它需要了解 pdftotext 与 PyMuPDF
- 构建 MCP 服务器？它需要协议规范和最佳实践
- 代码审查？它需要系统的检查清单

这种知识不是工具——它是**专业知识**。技能通过允许模型按需加载领域知识来解决这个问题。

范式转变：知识外置
--------------------------------------------
传统 AI：知识锁定在模型参数中
  - 教授新技能：收集数据 -> 训练 -> 部署
  - 成本：$10K-$1M+，时间：数周
  - 需要 ML 专业知识，GPU 集群

技能：知识存储在可编辑文件中
  - 教授新技能：编写一个 SKILL.md 文件
  - 成本：免费，时间：几分钟
  - 任何人都可以做

这就像是在没有任何训练的情况下附加一个热插拔的 LoRA 适配器！

工具 vs 技能：
---------------
    | 概念      | 它是什么                | 示例                       |
    |-----------|-------------------------|---------------------------|
    | **工具**  | 模型**能**做什么        | bash, read_file, write    |
    | **技能**  | 模型**知道**怎么做      | PDF 处理, MCP 开发        |

工具是能力。技能是知识。

渐进式披露：
----------------------
    第 1 层：元数据（始终加载）            ~100 token/技能
             仅名称 + 描述

    第 2 层：SKILL.md 正文（触发时）       ~2000 token
             详细说明

    第 3 层：资源（按需）                  无限制
             scripts/, references/, assets/

这保持了上下文精简，同时允许任意深度。

SKILL.md 标准：
-----------------
    skills/
    |-- pdf/
    |   |-- SKILL.md          # 必须：YAML frontmatter + Markdown 正文
    |-- mcp-builder/
    |   |-- SKILL.md
    |   |-- references/       # 可选：文档，规范
    |-- code-review/
        |-- SKILL.md
        |-- scripts/          # 可选：辅助脚本

保留缓存的注入：
--------------------------
关键见解：技能内容进入 tool_result（用户消息），
**而不是**系统提示词。这保留了提示词缓存！

    错误：每次编辑系统提示词（缓存失效，成本增加 20-50 倍）
    正确：将技能追加为工具结果（前缀不变，缓存命中）

这就是生产环境 Claude Code 的工作方式——也是它具有成本效益的原因。

用法：
    python v4_skills.py

样例：统计当前目录下的代码行数和功能，并且做 code-review，将结论输出到 html 中
"""

import re
import sys
import time
import traceback
from pathlib import Path
from llm_factory import LLMFactory, LLMChatAdapter
from util.mylog import logger
from utils import execute_base_tools, TodoManager, AGENT_TYPES, get_agent_descriptions, SUBAGENT_ALL_TOOLS, BASE_TOOLS

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
SKILLS_DIR = WORKDIR / "skills"

class SkillLoader:
    """
    从 SKILL.md 文件加载和管理技能。

    技能是一个包含以下内容的文件夹：
    - SKILL.md (必须): YAML frontmatter + markdown 说明
    - scripts/ (可选): 模型可以运行的辅助脚本
    - references/ (可选): 额外的文档
    - assets/ (可选): 模板，输出文件

    SKILL.md 格式：
    ----------------
        ---
        name: pdf
        description: Process PDF files. Use when reading, creating, or merging PDFs.
        ---

        # PDF Processing Skill

        ## Reading PDFs

        Use pdftotext for quick extraction:
        ```bash
        pdftotext input.pdf -
        ```
        ...

    YAML frontmatter 提供元数据（名称，描述）。
    Markdown 正文提供详细说明。
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills = {}
        self.load_skills()

    def parse_skill_md(self, path: Path) -> dict:
        content = path.read_text()

        # Match YAML frontmatter between --- markers
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not match:
            return None

        frontmatter, body = match.groups()

        # Parse YAML-like frontmatter (simple key: value)
        metadata = {}
        for line in frontmatter.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip().strip("\"'")

        # Require name and description
        if "name" not in metadata or "description" not in metadata:
            return None

        return {
            "name": metadata["name"],
            "description": metadata["description"],
            "body": body.strip(),
            "path": path,
            "dir": path.parent,
        }

    def load_skills(self):
        if not self.skills_dir.exists():
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            skill = self.parse_skill_md(skill_md)
            if skill:
                self.skills[skill["name"]] = skill

    def get_descriptions(self) -> str:
        if not self.skills:
            return "(no skills available)"

        return "\n".join(
            f"- {name}: {skill['description']}"
            for name, skill in self.skills.items()
        )

    def get_skill_content(self, name: str) -> str:
        if name not in self.skills:
            return None

        skill = self.skills[name]
        content = f"# Skill: {skill['name']}\n\n{skill['body']}"

        resources = []
        for folder, label in [
            ("scripts", "Scripts"),
            ("references", "References"),
            ("assets", "Assets")
        ]:
            folder_path = skill["dir"] / folder
            if folder_path.exists():
                files = list(folder_path.glob("*"))
                if files:
                    resources.append(f"{label}: {', '.join(f.name for f in files)}")

        if resources:
            content += f"\n\n**Available resources in {skill['dir']}:**\n"
            content += "\n".join(f"- {r}" for r in resources)

        return content

    def list_skills(self) -> list:
        return list(self.skills.keys())


SKILLS = SkillLoader(SKILLS_DIR)
TODO = TodoManager()

SYSTEM = f"""你是一个位于 {WORKDIR} 的编码代理，系统为 {sys.platform}。

## 执行流程
计划（使用 TodoWrite） -> 使用工具行动 -> 报告。

**可用技能**（当任务匹配时使用 Skill 工具调用）：
{SKILLS.get_descriptions()}

**可用子代理**（对于需要集中注意力的子任务，使用 Task 工具调用）：
{get_agent_descriptions()}

规则：
- 当任务匹配技能描述时，**立即**使用 Skill 工具
- 对需要集中探索或实现的子任务使用 Task 工具
- 使用 TodoWrite 跟踪多步骤工作
- 优先使用工具而不是文字描述。先行动，不要只是解释。
- 完成后，总结变更内容。"""

# NEW in v4: Skill tool
SKILL_TOOL = {
    "name": "Skill",
    "description": f"""Load a skill to gain specialized knowledge for a task.

Available skills:
{SKILLS.get_descriptions()}

When to use:
- IMMEDIATELY when user task matches a skill description
- Before attempting domain-specific work (PDF, MCP, etc.)

The skill content will be injected into the conversation, giving you
detailed instructions and access to resources.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": "Name of the skill to load"
            }
        },
        "required": ["skill"],
    },
}

ALL_TOOLS = SUBAGENT_ALL_TOOLS + [SKILL_TOOL]
max_steps = 50

def get_tools_for_agent(agent_type: str) -> list:
    allowed = AGENT_TYPES.get(agent_type, {}).get("tools", "*")

    if allowed == "*":
        return BASE_TOOLS  # All base tools, but NOT Task (no recursion in demo)

    return [t for t in BASE_TOOLS if t["name"] in allowed]

def run_subagent_task(description: str, prompt: str, agent_type: str, max_steps: int = max_steps) -> str:
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

def run_skill(skill_name: str) -> str:
    """
    加载一项技能并将其注入到对话中。

    这是关键机制：
    1. 获取技能内容（SKILL.md 正文 + 资源提示）
    2. 将其包装在 <skill-loaded> 标签中返回
    3. 模型作为 tool_result（用户消息）接收此内容
    4. 模型现在"知道"如何执行任务

    为什么使用 tool_result 而不是系统提示词？
    - 系统提示词更改会使缓存失效（成本增加 20-50 倍）
    - 工具结果追加到末尾（前缀不变，缓存命中）

    这就是生产系统保持成本效益的方式。
    """
    content = SKILLS.get_skill_content(skill_name)

    if content is None:
        available = ", ".join(SKILLS.list_skills()) or "none"
        return f"Error: Unknown skill '{skill_name}'. Available: {available}"

    # Wrap in tags so model knows it's skill content
    return f"""<skill-loaded name="{skill_name}">
{content}
</skill-loaded>

Follow the instructions in the skill above to complete the user's task."""

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
        try:
            return run_subagent_task(args["description"], args["prompt"], args["agent_type"])
        except Exception as e:
            return f"Error: {e}"

    if name == "Skill":
        try:
            return run_skill(args["skill"])
        except Exception as e:
            return f"Error: {e}"

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
            tools=ALL_TOOLS,
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
            elif tc.name == "Skill":
                logger.info(f"\n> [使用工具] 第 {step} 步调用 Loading skill: {tc.input.get('skill', '?')}")
            else:
                logger.info(f"\n> [使用工具] {tc.name} 第 {step} 步调用: {tc.input}")

            output = execute_tool(tc.name, tc.input)

            if tc.name == "Skill":
                logger.info(f"  Skill loaded ({len(output)} chars)")
            elif tc.name != "Task":
                preview = output[:200] + "..." if len(output) > 200 else output
                logger.info(f"  [使用工具] {tc.name}, 返回: {preview}")

            results.append(f"工具 {tc.name}, 输入: {tc.input}, 返回: {output}")

        history.append({"role": "assistant", "content": full_text})
        combined_output = "\n".join(results)
        history.append({"role": "user", "content": f"执行结果：\n{combined_output}\n\n请继续处理"})

def main():
    logger.info(f"Mini Claude Code v4 (with Skills) - {WORKDIR}")
    logger.info(f"Skills: {', '.join(SKILLS.list_skills()) or 'none'}")
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