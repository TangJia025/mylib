import subprocess
import sys
import time
from pathlib import Path
from util.mylog import logger

WORKDIR = Path.cwd()

def safe_path(p: str) -> Path:
    """
    Ensure path stays within workspace (security measure).

    Prevents the model from accessing files outside the project directory.
    Resolves relative paths and checks they don't escape via '../'.
    """
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(cmd: str) -> str:
    """Execute shell command with safety checks."""
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot"]
    if any(d in cmd for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=WORKDIR,
            capture_output=True, text=True, timeout=120
        )
        output = (result.stdout + result.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout"
    except Exception as e:
        return f"Error: {e}"

def run_read(path: str, limit: int = None) -> str:
    """Read file contents."""
    try:
        text = safe_path(path).read_text()
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(text.splitlines()) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    """Write content to file."""
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    """Replace exact text in file."""
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        # Replace only first occurrence for safety
        new_content = content.replace(old_text, new_text, 1)
        fp.write_text(new_content)
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

def execute_base_tools(name: str, args: dict, todo_manager=None) -> str:
    """Execute standard tools (bash, read, write, edit)."""
    if name == "bash":
        if "command" not in args:
            return "Error: bash command required"
        return run_bash(args["command"])

    if name == "read_file":
        if "path" not in args:
            return "Error: read_file path required"
        if "limit" in args and not isinstance(args["limit"], int):
            return "Error: limit must be an integer"
        return run_read(args["path"], args.get("limit"))

    if name == "write_file":
        if "path" not in args:
            return "Error: write_file path required"
        if "content" not in args:
            return "Error: write_file content required"
        return run_write(args["path"], args["content"])

    if name == "edit_file":
        if "path" not in args:
            return "Error: edit_file path required"
        if "old_text" not in args:
            return "Error: edit_file old_text required"
        if "new_text" not in args:
            return "Error: edit_file new_text required"
        return run_edit(args["path"], args["old_text"], args["new_text"])

    if name == "TodoWrite" and todo_manager:
        if "items" not in args:
            return "Error: TodoWrite items required"
        return todo_manager.update(args["items"])

    return None

class TodoManager:
    """Task list manager with constraints."""
    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        validated = []
        in_progress_count = 0

        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            active_form = str(item.get("activeForm", "")).strip()

            if not content:
                raise ValueError(f"Item {i}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if not active_form:
                raise ValueError(f"Item {i}: activeForm required")

            if status == "in_progress":
                in_progress_count += 1

            validated.append({
                "content": content,
                "status": status,
                "activeForm": active_form
            })

        if len(validated) > 20:
            raise ValueError("Max 20 todos allowed")
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress at a time")

        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."

        lines = []
        for item in self.items:
            if item["status"] == "completed":
                lines.append(f"[x] {item['content']}")
            elif item["status"] == "in_progress":
                lines.append(f"[>] {item['content']} <- {item['activeForm']}")
            else:
                lines.append(f"[ ] {item['content']}")

        completed = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({completed}/{len(self.items)} completed)")

        return "\n".join(lines)

AGENT_TYPES = {
    "explore": {
        "description": "Read-only agent for exploring code, finding files, searching",
        "tools": ["bash", "read_file"],
        "prompt": "You are an exploration agent. Search and analyze, but never modify files. Return a concise summary.",
    },
    "code": {
        "description": "Full agent for implementing features and fixing bugs",
        "tools": "*",
        "prompt": "You are a coding agent. Implement the requested changes efficiently.",
    },
    "plan": {
        "description": "Planning agent for designing implementation strategies",
        "tools": ["bash", "read_file"],
        "prompt": "You are a planning agent. Analyze the codebase and output a numbered implementation plan. Do NOT make changes.",
    },
}

def get_agent_descriptions() -> str:
    return "\n".join(
        f"- {name}: {cfg['description']}"
        for name, cfg in AGENT_TYPES.items()
    )

# =============================================================================
# Tool Definitions
# =============================================================================

BASH_TOOLS = [
    {
        "name": "bash",
        "description": '''
Execute shell command. Common patterns:
- Read: cat/head/tail, grep/find/rg/ls, wc -l
- Write: echo 'content' > file, sed -i 's/old/new/g' file
''',
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    }
]

BASIC_TOOLS = BASH_TOOLS + [
    {
        "name": "read_file",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write to file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace text in file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
]

TODO_TOOL = {
    "name": "TodoWrite",
    "description": "Update the task list. Use to plan and track progress.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "Complete list of tasks (replaces existing)",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"]
                        },
                        "activeForm": {"type": "string"},
                    },
                    "required": ["content", "status", "activeForm"],
                },
            }
        },
        "required": ["items"],
    },
}

BASE_TOOLS = BASIC_TOOLS + [TODO_TOOL]

TASK_TOOL = {
    "name": "Task",
    "description": f"""Spawn a subagent for a focused subtask.

Subagents run in ISOLATED context - they don't see parent's history.
Use this to keep the main conversation clean.

Agent types:
{get_agent_descriptions()}

Example uses:
- Task(explore): "Find all files using the auth module"
- Task(plan): "Design a migration strategy for the database"
- Task(code): "Implement the user registration form"
""",
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Short task name (3-5 words) for progress display"
            },
            "prompt": {
                "type": "string",
                "description": "Detailed instructions for the subagent"
            },
            "agent_type": {
                "type": "string",
                "enum": list(AGENT_TYPES.keys()),
                "description": "Type of agent to spawn"
            },
        },
        "required": ["description", "prompt", "agent_type"],
    },
}

SUBAGENT_ALL_TOOLS = BASE_TOOLS + [TASK_TOOL]

class TodoManager:
    """
    管理具有强制约束的结构化任务列表。

    关键设计决策：
    --------------------
    1. 最多 20 项：防止模型创建无尽的列表
    2. 一个进行中：强制专注 - 一次只能做一件事
    3. 必填字段：每个项目需要 content, status 和 activeForm

    activeForm 字段值得解释：
    - 它是正在发生的事情的现在时形式
    - 当 status 为 "in_progress" 时显示
    - 示例：content="Add tests", activeForm="Adding unit tests..."

    这提供了代理正在做什么的实时可见性。
    """

    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        """
        验证并更新任务列表。

        模型每次发送一个完整的列表。我们验证它，
        存储它，并返回一个模型将看到的渲染视图。

        验证规则：
        - 每个项目必须有：content, status, activeForm
        - Status 必须是：pending | in_progress | completed
        - 一次只能有 ONE 个项目处于 in_progress 状态
        - 最多允许 20 个项目

        Returns:
            任务列表的渲染文本视图
        """
        validated = []
        in_progress_count = 0

        for i, item in enumerate(items):
            # Extract and validate fields
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            active_form = str(item.get("activeForm", "")).strip()

            # Validation checks
            if not content:
                raise ValueError(f"Item {i}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if not active_form:
                raise ValueError(f"Item {i}: activeForm required")

            if status == "in_progress":
                in_progress_count += 1

            validated.append({
                "content": content,
                "status": status,
                "activeForm": active_form
            })

        # Enforce constraints
        if len(validated) > 20:
            raise ValueError("Max 20 todos allowed")
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress at a time")

        self.items = validated
        return self.render()

    def render(self) -> str:
        """
        将任务列表渲染为人类可读的文本。

        格式：
            [x] 已完成任务
            [>] 进行中任务 <- 正在做某事...
            [ ] 待办任务

            (2/3 completed)

        这个渲染后的文本是模型作为工具结果看到的内容。
        然后它可以根据当前状态更新列表。
        """
        if not self.items:
            return "No todos."

        lines = []
        for item in self.items:
            if item["status"] == "completed":
                lines.append(f"[x] {item['content']}")
            elif item["status"] == "in_progress":
                lines.append(f"[>] {item['content']} <- {item['activeForm']}")
            else:
                lines.append(f"[ ] {item['content']}")

        completed = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({completed}/{len(self.items)} completed)")

        return "\n".join(lines)

def get_tools_for_agent(agent_type: str) -> list:
    """Filter tools based on agent type."""
    allowed = AGENT_TYPES.get(agent_type, {}).get("tools", "*")
    if allowed == "*":
        return BASE_TOOLS
    return [t for t in BASE_TOOLS if t["name"] in allowed]