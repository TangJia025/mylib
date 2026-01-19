from util.mylog import logger
from typing import Any, List, Mapping, Optional, Dict
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks import CallbackManagerForLLMRun
from pydantic import Field
from zhipu.zhipu_text import ZhipuTextAPI
from util.llm_utils import process_llm_response

class ZhipuLLM(LLM):
    """智谱 AI 大模型的 LangChain LLM 实现"""
    
    client: ZhipuTextAPI = Field(default_factory=ZhipuTextAPI)
    model_name: str = Field(default="glm-4")
    temperature: Optional[float] = Field(default=0.6)
    top_p: Optional[float] = Field(default=0.9)
    max_tokens: Optional[int] = Field(default=None)
    
    class Config:
        arbitrary_types_allowed = True
    
    @property
    def _llm_type(self) -> str:
        """返回 LLM 类型"""
        return "zhipu"
    
    @property
    def _supported_params(self) -> List[str]:
        """Return supported parameters."""
        return ["temperature", "top_p", "max_tokens", "model"]
    
    @property
    def _default_params(self) -> Dict[str, Any]:
        """Get the default parameters for calling Zhipu API."""
        return {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 4096,
            "model": "glm-4"
        }
        
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """执行 LLM 调用，支持文本和图像输入"""
        image = kwargs.pop("image", None)
        kwargs.pop("tools", None)
        
        if image is not None:
            response = self.client.generate_text_with_image(
                prompt=prompt,
                image=image,
                model="glm-4v",  # 使用多模态模型
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                **kwargs
            )
        else:
            response = self.client.generate_text(
                prompt=prompt,
                model=self.model_name,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                stop=stop[0] if stop else None,
                **kwargs
            )
        
        result = process_llm_response(response)
        logger.info(f"LLM Response: {result}")
        return result
        
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """获取模型标识参数"""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens
        }

if __name__ == "__main__":
    logger.info("测试智谱大模型")
    llm = ZhipuLLM()
    
    # 测试文本生成
    logger.info("测试文本生成：")
    logger.info(llm("你好，我是智谱大模型"))
    
    # 测试图文生成
    # from PIL import Image
