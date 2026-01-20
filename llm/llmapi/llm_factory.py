from typing import Optional, Dict, Any, List, Tuple
from langchain_core.language_models.llms import LLM
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from get_model_list import SUPPORTED_MODELS
from util.llm_plugin import Plugin, ReplaceImagePlugin
from util.mylog import logger
from util.llm_utils import safe_literal_eval

class LLMChatAdapter:
    """适配器类，将LLM对象包装成具有appendSystemInfo和chat方法的接口"""
    
    def __init__(self, llm: LLM, keep_messages_count: int = 20) -> None:
        self.llm = llm
        self.system_info = ""
        self.keep_messages_count = keep_messages_count  # 保留最近N条消息
        try:
            self.plugins: List[Plugin] = [ReplaceImagePlugin()]
        except Exception as e:
            logger.warning(f"插件初始化失败: {str(e)}")
            self.plugins: List[Plugin] = []
        
    def appendSystemInfo(self, system_info: str) -> None:
        """添加系统提示信息"""
        self.system_info = system_info
        
    def chat(self, prompt: str, image: str = None, messages: List[Dict[str, str]] = None, **kwargs) -> Tuple[bool, str]:
        """
        与LLM进行对话
        
        Args:
            prompt: 用户输入的提示
            image: 可选的图片参数
            messages: 可选的历史消息列表，格式为 [{"role": "user/assistant/system", "content": "消息内容"}, ...]
            **kwargs: 传递给LLM调用的其他参数(如tools)
            
        Returns:
            Tuple[bool, str]: (是否成功, 响应内容或错误信息)
        """
        # 确定消息来源：优先使用messages参数，否则使用prompt（如果是列表格式）
        history_messages = messages if messages else (prompt if isinstance(prompt, list) else None)

        try:
            for plugin in self.plugins:
                prompt = plugin.process_input(prompt)
        except Exception as e:
            logger.warning(f"插件处理输入失败: {str(e)}")
            
        success = True
        response = None
        try:
            # 构建langchain消息列表
            langchain_messages = self._build_langchain_messages(history_messages, prompt)
            logger.info(f"[chat] Messages count: {len(langchain_messages)}, prompt len: {len(prompt)}")
            response = self.llm.invoke(langchain_messages, image=image, **kwargs)
            logger.info(f"[chat] LLM响应长度: {len(response)}")
        except Exception as e:
            success = False
            response = f"LLM调用出错: {str(e)}"
            logger.error(response)
            
        if success:
            try:
                for plugin in self.plugins:
                    response = plugin.process_output(response)
            except Exception as e:
                logger.warning(f"插件处理输出失败: {str(e)}")
                
        return success, response

    def _build_langchain_messages(self, history_messages: List[Dict[str, str]], prompt_text: str) -> List:
        """
        构建langchain格式的消息列表
        """
        messages = []
        
        # 添加系统消息
        if self.system_info:
            messages.append(SystemMessage(content=self.system_info))
        
        # 如果没有历史消息，直接使用 prompt_text
        if not history_messages:
            messages.append(HumanMessage(content=prompt_text))
            return messages

        # 处理历史消息
        # 只保留最近N条消息
        recent_messages = history_messages[-self.keep_messages_count:] if len(history_messages) > self.keep_messages_count else history_messages
        
        for msg in recent_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                messages.append(SystemMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            else:  # user 或其他角色
                messages.append(HumanMessage(content=content))
        
        return messages
    
    def literal_eval(self, response, replace_list: List[str] = None) -> Any:
        """
        安全地将LLM响应解析为Python对象
        (Delegates to util.llm_utils.safe_literal_eval)
        """
        return safe_literal_eval(response, replace_list)

    # 工具调用
    def chat_with_tools(self, prompt: str, messages: List[Dict[str, str]], tools: List[Dict] = None, system: str = None, **kwargs) -> Any:
        """
        支持工具调用的对话接口，返回格式兼容 Anthropic SDK 的 Response 对象。
        
        Args:
            messages: 消息列表
            tools: 工具定义列表 (支持 Anthropic 格式)
            system: 系统提示词
            **kwargs: 其他参数
            
        Returns:
            Response 对象，包含 content (blocks) 和 stop_reason
        """
        if system:
            self.appendSystemInfo(system)
            
        converted_tools = []
        if tools:
            for t in tools:
                if isinstance(t, dict):
                    # Check if it's already in the expected format or needs conversion
                    if "type" in t and t["type"] == "function":
                        logger.info("case 1")
                        converted_tools.append(t)
                    elif "input_schema" in t:
                        logger.info("case 2")
                        converted_tools.append({
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "description": t["description"],
                                "parameters": t.get("input_schema", {})
                            }
                        })
                    else:
                         logger.info("case 3")
                        # Fallback: assume it's simple definition or already close to function
                         converted_tools.append({
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "description": t.get("description", ""),
                                "parameters": t.get("parameters", {})
                            }
                        })

        try:
            success, content = self.chat(
                prompt=prompt,
                messages=messages,
                tools=converted_tools,
                **kwargs
            )
        except Exception as e:
            success = False
            content = str(e)

        logger.info(f"jjj chat_with_tools success: {success}, content : {content}")  

        blocks = []
        stop_reason = "end_turn"
        
        if success:
            import json
            try:
                # content might be a json string if it's a tool call
                data = json.loads(content)
                tool_list = []
                is_tool_call = False

                # Check for new dict format (content + tool_calls)
                if isinstance(data, dict) and "tool_calls" in data and isinstance(data["tool_calls"], list):
                    is_tool_call = True
                    stop_reason = "tool_use"
                    if data.get("content"):
                        logger.info("case A")
                        blocks.append(type("TextBlock", (), {"type": "text", "text": data["content"]}))
                    tool_list = data["tool_calls"]
                
                # Check if it looks like a tool call list (Legacy)
                elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and ("function" in data[0] or "type" in data[0]):
                    logger.info("case B")
                    is_tool_call = True
                    stop_reason = "tool_use"
                    tool_list = data

                if is_tool_call:
                    for tc in tool_list:
                        # Handle both OpenAI format (has 'function')
                        if "function" in tc:
                            func_data = tc["function"]
                            args = func_data["arguments"]
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except:
                                    pass
                                
                            logger.info("case X")
                            logger.info(f"Tool call detected: {func_data['name']} with args: {args}")
                            blocks.append(type("ToolUseBlock", (), {
                                "type": "tool_use",
                                "id": tc.get("id", "call_1"),
                                "name": func_data["name"],
                                "input": args
                            }))
                else:
                     logger.info("case Y")
                     blocks.append(type("TextBlock", (), {"type": "text", "text": content}))
            except:
                # Not JSON, treat as text
                logger.info("case Z")
                blocks.append(type("TextBlock", (), {"type": "text", "text": content}))
        else:
             blocks.append(type("TextBlock", (), {"type": "text", "text": f"Error: {content}"}))

        return type("Response", (), {"content": blocks, "stop_reason": stop_reason})
            
class LLMFactory:
    """LLM工厂类，用于创建不同类型的LLM实例"""
    _instances: Dict[Tuple[str, str], LLM] = {}
    
    @classmethod
    def create(
        cls,
        model_type: str,
        model_name: Optional[str] = None,
        temperature: Optional[float] = 0.6,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = 60000,
        **kwargs: Dict[str, Any]
    ) -> LLM:
        """
        创建LLM实例
        """
        # 参数验证
        if temperature is not None and not 0 <= temperature <= 2:
            raise ValueError("temperature 必须在 0 到 2 之间")
        if top_p is not None and not 0 <= top_p <= 1:
            raise ValueError("top_p 必须在 0 到 1 之间")
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError("max_tokens 必须大于 0")
        
        # 规范化缓存键（按类型+名称）
        key = (str(model_type).lower().strip(), str(model_name or "").lower().strip())
        if key in cls._instances:
            return cls._instances[key]
        
        # 获取模型类
        model_class = SUPPORTED_MODELS.get(model_type)
        if not model_class:
            raise ValueError(f"不支持的模型类型: {model_type}，支持的类型: {list(SUPPORTED_MODELS.keys())}")
        
        logger.info(f"====== 使用 {model_type} 模型: {model_name}, 参数:({temperature}, {top_p}, {max_tokens})")
        # 创建实例并缓存
        instance = model_class(
            model_name=model_name,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            **kwargs
        )
        cls._instances[key] = instance
        return instance

if __name__ == "__main__":
    # 测试不同类型的模型
    test_prompts = [
        ("qianfan", "deepseek-v3"),
        ("huggingface", "Qwen/Qwen2.5-0.5B-Instruct"),
        ("openai", "claude-haiku-4.5"),
        ("qwen", "qwen/qwen-plus"),
        ("zhipu", "glm-4"),
        ("siliconflow", "deepseek-v3.2"),
    ]
    
    # 测试 tools
    logger.info("测试 tools 功能")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Get the current weather in a given location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state, e.g. San Francisco, CA",
                        },
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    for model_type, model_name in test_prompts:
        try:
            logger.info(f"\n测试 {model_type} 模型: {model_name}")
            llm = LLMFactory.create(
                model_type=model_type,
                model_name=model_name,
                temperature=0.6,
                max_tokens=1000,
            )
            llm_adapter = LLMChatAdapter(llm)
            
            # 测试原始 chat 方法
            logger.info(">>> 测试原始 chat 方法:")
            isok, response = llm_adapter.chat("What's the weather like in Boston today?")
            logger.info(f"原始响应: {response}, isok: {isok}")

            # 测试新 chat_with_tools 方法
            logger.info(">>> 测试 chat_with_tools 方法:")
            response_obj = llm_adapter.chat_with_tools(
                messages=[{"role": "user", "content": "What's the weather like in Boston today?"}], 
                tools=tools
            )
            logger.info(f"chat_with_tools 响应: stop_reason={response_obj.stop_reason}")
            for block in response_obj.content:
                if getattr(block, "type", "") == "text":
                    logger.info(f"Text Block: {block.text}")
                elif getattr(block, "type", "") == "tool_use":
                    logger.info(f"Tool Use Block: name={block.name}, input={block.input}, id={block.id}")
                else:
                    logger.info(f"Unknown Block: {block}")
        except Exception as e:
            logger.error(f"{model_type} 模型测试失败: {str(e)}")
