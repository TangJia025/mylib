import streamlit as st

from translation.translation import TranslationAgent
from llmapi.llm_factory import LLMFactory, LLMChatAdapter
from llmapi.util.mylog import logger

class AppUI:
    def __init__(self):
        self.translator = None
        self.llm_chat_adapter = None
        
    def initialize_model(self, model_type, model_name, temperature, top_p):
        """初始化模型"""
        try:
            llm = LLMFactory.create(model_type, model_name=model_name, temperature=temperature, top_p=top_p)
            self.translator = TranslationAgent(llm)
            self.llm_chat_adapter = LLMChatAdapter(llm)
            logger.info(f"模型 {model_type}/{model_name} 初始化成功")
            return f"✅ 模型 {model_type}/{model_name} 初始化成功"
        except Exception as e:
            return f"❌ 模型初始化失败: {str(e)}"
    
    def translate_text(self, source_lang, target_lang, source_text, country=""):
        """执行翻译"""
        if not self.translator:
            return "❌ 请先初始化模型"
        if not source_text.strip():
            return "❌ 请输入要翻译的文本"
        
        try:
            return self.translator.translate(source_lang, target_lang, source_text, country, self.llm_chat_adapter)
        except Exception as e:
            logger.error(f"翻译失败: {str(e)}")
            return f"❌ 翻译失败: {str(e)}"
    
    def chat_with_agent(self, message, history):
        """与智能体对话"""
        if not self.llm_chat_adapter:
            return history, ""
        
        try:
            # 构建对话上下文
            conversation = ""
            for msg in history:
                if msg["role"] == "user":
                    conversation += f"用户: {msg['content']}\n"
                elif msg["role"] == "assistant":
                    conversation += f"助手: {msg['content']}\n"
            
            # 添加当前用户消息
            conversation += f"用户: {message}\n助手: "
            
            # 获取回复 - LLMChatAdapter.chat 返回 (bool, str) 元组
            success, response = self.llm_chat_adapter.chat(conversation)
            
            if not success:
                response = f"对话失败: {response}"
            
            # 更新历史记录
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response})
            
            return history, ""
        except Exception as e:
            error_msg = f"对话失败: {str(e)}"
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": error_msg})
            return history, ""
    
    def render_streamlit(self):
        st.set_page_config(page_title="AI 助手", layout="wide")
        if "ui" not in st.session_state:
            st.session_state.ui = self
        if "init_status" not in st.session_state:
            st.session_state.init_status = ""
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        st.title("🤖 AI 助手")
        col1, col2 = st.columns([2, 1])
        with col1:
            mt = st.selectbox("模型类型", ["qianfan", "openai", "qwen", "zhipu", "ollama", "siliconflow"], index=0)
            mn = st.text_input("模型名称", value="deepseek-v3")
            t = st.slider("Temperature", 0.0, 2.0, 0.6, 0.1)
            p = st.slider("Top-p", 0.0, 1.0, 0.9, 0.05)
            if st.button("初始化模型"):
                st.session_state.init_status = self.initialize_model(mt, mn, t, p)
        with col2:
            st.text_area("状态", value=st.session_state.init_status, height=100)

        tab_chat, tab_trans = st.tabs(["对话", "翻译"])
        with tab_chat:
            for msg in st.session_state.chat_history:
                with st.chat_message("user" if msg["role"] == "user" else "assistant"):
                    st.markdown(msg["content"])
            user_input = st.chat_input("请输入您的问题...")
            if user_input:
                history = st.session_state.chat_history
                if not self.llm_chat_adapter:
                    history.append({"role": "assistant", "content": "❌ 请先初始化模型"})
                else:
                    conversation = ""
                    for m in history:
                        if m["role"] == "user":
                            conversation += f"用户: {m['content']}\n"
                        elif m["role"] == "assistant":
                            conversation += f"助手: {m['content']}\n"
                    conversation += f"用户: {user_input}\n助手: "
                    ok, resp = self.llm_chat_adapter.chat(conversation)
                    if not ok:
                        resp = f"对话失败: {resp}"
                    history.append({"role": "user", "content": user_input})
                    history.append({"role": "assistant", "content": resp})
                try:
                    st.rerun()
                except Exception:
                    try:
                        st.experimental_rerun()
                    except Exception:
                        pass

        with tab_trans:
            cols = st.columns(3)
            with cols[0]:
                src = st.selectbox("源语言", ["English", "Chinese", "Japanese", "Korean", "French", "German", "Spanish", "Russian"], index=0)
            with cols[1]:
                tgt = st.selectbox("目标语言", ["Chinese", "English", "Japanese", "Korean", "French", "German", "Spanish", "Russian"], index=1)
            with cols[2]:
                country = st.text_input("地区 (可选)", value="")
            source_text = st.text_area("待翻译文本", height=160, placeholder="请输入要翻译的文本...")
            if st.button("开始翻译"):
                result = self.translate_text(src, tgt, source_text, country)
                st.text_area("翻译结果", value=result, height=160)

if __name__ == "__main__":
    ui = AppUI()
    ui.render_streamlit()