"""
Embeddings - 向量化工具

使用 LLM Gateway 生成文本嵌入向量
"""

from typing import List, Optional

try:
    from agent.models.llm_gateway import LLMGateway
    from agent.config.config_service import AgentConfigService
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False
    LLMGateway = None
    AgentConfigService = None


class EmbeddingsGenerator:
    """文本嵌入向量生成器

    使用 LLM 生成文本的嵌入向量。
    由于各 LLM API 不提供独立的 embedding 接口，
    这里使用一个简化的方法：对文本进行分块，通过 LLM 生成特征向量。
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        """
        初始化嵌入生成器

        Args:
            llm_gateway: LLM 网关实例，如果为 None 则使用默认配置创建
        """
        if llm_gateway is None and AGENT_AVAILABLE:
            config_service = AgentConfigService()
            llm_gateway = LLMGateway(config_service)
        self.llm_gateway = llm_gateway

    async def generate_text_embedding(self, text: str, dimensions: int = 1536) -> List[float]:
        """
        生成文本嵌入向量

        使用 LLM 分析文本并生成一个简化的向量表示。
        注意：这是一个近似方法，真正的 embedding 应该使用专门的 embedding 模型。

        Args:
            text: 输入文本
            dimensions: 向量维度（默认 1536，与 OpenAI text-embedding-ada-002 一致）

        Returns:
            嵌入向量
        """
        if not self.llm_gateway:
            # 如果没有 LLM 网关，返回一个基于文本长度的伪向量
            return self._generate_fallback_embedding(text, dimensions)

        try:
            # 使用 LLM 分析文本特征
            prompt = f"""分析以下文本，提取其语义特征向量。
返回一个 {dimensions} 维的特征向量，表示为 JSON 数组格式。
只返回数组，不要其他内容。

文本内容：
{text[:1000]}"""

            from agent.models.llm_gateway import LLMRequest
            request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2000,
            )

            response = await self.llm_gateway.invoke(request)

            if response.success and response.data:
                import json
                try:
                    # 尝试解析 LLM 返回的向量
                    embedding = json.loads(response.data)
                    if isinstance(embedding, list) and len(embedding) == dimensions:
                        return embedding
                except (json.JSONDecodeError, ValueError):
                    pass

            # 如果解析失败，使用回退方法
            return self._generate_fallback_embedding(text, dimensions)

        except Exception as e:
            print(f"Failed to generate embedding: {e}")
            return self._generate_fallback_embedding(text, dimensions)

    def _generate_fallback_embedding(self, text: str, dimensions: int) -> List[float]:
        """
        生成回退嵌入向量

        当 LLM 不可用时使用。基于文本的统计特征生成一个伪向量。
        """
        import hashlib

        # 使用文本的 hash 作为种子
        text_hash = hashlib.md5(text.encode()).digest()
        seed = int.from_bytes(text_hash[:4], 'big')

        # 基于文本长度和内容生成伪向量
        vec = []
        for i in range(dimensions):
            # 使用简单的伪随机生成
            seed = (seed * 1103515245 + 12345) & 0x7fffffff
            value = (seed % 1000) / 1000.0

            # 加入文本特征
            if i < len(text):
                value = (value + ord(text[i]) / 255.0) / 2.0

            vec.append(value)

        # 归一化
        magnitude = sum(v * v for v in vec) ** 0.5
        if magnitude > 0:
            vec = [v / magnitude for v in vec]

        return vec

    async def generate_query_vector(self, query: str) -> List[float]:
        """
        生成查询向量（用于搜索）

        Args:
            query: 查询文本

        Returns:
            查询向量
        """
        return await self.generate_text_embedding(query)


# 全局嵌入生成器实例
_embeddings_generator: Optional[EmbeddingsGenerator] = None


def get_embeddings_generator() -> EmbeddingsGenerator:
    """获取全局嵌入生成器实例"""
    global _embeddings_generator
    if _embeddings_generator is None:
        _embeddings_generator = EmbeddingsGenerator()
    return _embeddings_generator


async def generate_embedding(text: str) -> List[float]:
    """
    生成文本嵌入向量的便捷函数

    Args:
        text: 输入文本

    Returns:
        嵌入向量
    """
    generator = get_embeddings_generator()
    return await generator.generate_text_embedding(text)
