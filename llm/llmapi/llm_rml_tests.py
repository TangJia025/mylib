from util.rlm_repl import RLM_REPL
from util.mylog import logger
import random

def generate_massive_context(num_lines: int = 1_000_000, answer: str = "1298418") -> str:
    logger.info(f"正在生成包含{num_lines}行的大规模上下文...")
    
    # 用于生成随机文本的词汇集合
    random_words = ["blah", "random", "text", "data", "content", "information", "sample"]
    
    lines = []
    for _ in range(num_lines):
        num_words = random.randint(3, 8)
        line_words = [random.choice(random_words) for _ in range(num_words)]
        lines.append(" ".join(line_words))
    
    # 在随机位置（中间某处）插入魔法数字
    magic_position = random.randint(0, num_lines-1)
    lines[magic_position] = f"魔法数字是 {answer}"
    
    logger.info(f"魔法数字已插入到位置 {magic_position}")
    
    return "\n".join(lines)

def main():
    from llm_factory import LLMFactory, LLMChatAdapter
    # 高级模型，拆解任务
    llm = LLMFactory.create(
        model_type="openai",
        model_name="claude-sonnet-4.5",
        temperature=0.7,
        max_tokens=8192
    )
    # 低级模型，执行具体任务
    nano_llm = LLMFactory.create(
        model_type="openai",
        model_name="claude-haiku-4.5",
        temperature=0.7,
        max_tokens=8192
    )
    llm_adapter = LLMChatAdapter(llm)
    nano_llm_adapter = LLMChatAdapter(nano_llm)
    logger.info("使用 RLM (REPL) 结合 GPT-5-nano 解决大海捞针问题的示例。")
    answer = str(random.randint(1000000, 9999999))
    context = generate_massive_context(num_lines=20, answer=answer)

    rlm = RLM_REPL(
        llm_client=llm_adapter,
        recursive_model=nano_llm_adapter,
        max_iterations=10
    )
    query = "我正在寻找一个魔法数字，它是什么？不需要其他信息，只需要输出魔法数字"
    result = rlm.completion(context=context, query=query)
    logger.info(f"结果: {result}。预期: {answer}")

if __name__ == "__main__":
    main()