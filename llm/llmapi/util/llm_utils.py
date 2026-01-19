import json
import ast
from typing import Any, List, Union, Tuple
from util.mylog import logger

def process_llm_response(response: Any) -> str:
    """
    Process the response from LLM API client.
    Handles error checking, content extraction, and tool/function call parsing.
    """
    if "error" in response:
        raise ValueError(f"API调用错误: {response['error']}")
        
    if "choices" not in response:
        raise ValueError("API响应格式错误")
    
    message = response["choices"][0]["message"]
    content = message.get("content")
    
    # Handle tool_calls with optional content (New Standard)
    if "tool_calls" in message and message["tool_calls"]:
        return json.dumps({
            "content": content or "",
            "tool_calls": message["tool_calls"]
        }, ensure_ascii=False)

    # Legacy: Handle tool_calls or function_call if content is None or empty
    if not content:
        if "tool_calls" in message:
            return json.dumps(message["tool_calls"], ensure_ascii=False)
        if "function_call" in message:
            return json.dumps(message["function_call"], ensure_ascii=False)
            
    return content if content is not None else ""

def safe_literal_eval(response: Union[str, Tuple[bool, str]], replace_list: List[str] = None) -> Any:
    """
    Safely parse LLM response into Python object.
    """
    # Handle tuple response (success, text)
    if isinstance(response, tuple) and len(response) == 2:
        success, text = response
        if not success:
            logger.warning(f"LLM响应失败: {text}")
            return []
    else:
        text = response
    
    if replace_list:
        for replace_str in replace_list:
            text = str(text).replace(replace_str, "")

    text_str = str(text).strip()
    try:
        return ast.literal_eval(text_str)
    except (ValueError, SyntaxError):
        try:
            # Try to find list brackets
            start = text_str.find('[')
            end = text_str.rfind(']')
            if start != -1 and end != -1:
                return ast.literal_eval(text_str[start:end + 1])
        except Exception as e:
            logger.warning(f"解析文本为Python对象失败: {str(e)}")
            
    return []
