#!/usr/bin/env python3
"""
测试 LLM 多模态分析图片
"""

import asyncio
import os
import sys
import json
import base64

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from agent.models.gateway_factory import GatewayFactory
from agent.models.llm_gateway import LLMRequest
from agent.config.config_service import AgentConfigService


def create_test_png():
    """创建一个简单的测试 PNG"""
    import zlib

    def png_chunk(chunk_type, data):
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return len(data).to_bytes(4, 'big') + chunk + crc.to_bytes(4, 'big')

    # 100x100 蓝色 PNG
    png_data = b'\x89PNG\r\n\x1a\n'
    ihdr_data = b'\x00\x00\x00\x64' + b'\x00\x00\x00\x64'
    ihdr_data += b'\x08\x02\x00\x00\x00'
    png_data += png_chunk(b'IHDR', ihdr_data)

    raw_data = b''
    for y in range(100):
        raw_data += b'\x00'
        for x in range(100):
            raw_data += b'\x00\x00\xff'

    compressed = zlib.compress(raw_data, 9)
    png_data += png_chunk(b'IDAT', compressed)
    png_data += png_chunk(b'IEND', b'')

    return png_data


async def test_llm_multimodal():
    """测试 LLM 多模态分析图片"""
    config_service = AgentConfigService()
    llm_gateway = GatewayFactory.get_gateway("llm", config_service)

    png_bytes = create_test_png()
    image_base64 = base64.b64encode(png_bytes).decode('utf-8')
    image_data_url = f"data:image/png;base64,{image_base64}"

    prompt = """请详细分析这张小红书文案图片，提取以下信息：

1. **文案结构**：标题格式、正文分段方式、标签使用
2. **风格特点**：整体语气、emoji使用频率、排版特点
3. **格式特征**：每段字数、特殊排版

请用 JSON 格式返回分析结果。"""

    messages = [
        {
            "role": "user",
            "content": [
                {"image": image_data_url},
                {"text": prompt}
            ]
        }
    ]

    print("=" * 60)
    print("测试 LLM 多模态分析图片")
    print("=" * 60)
    print(f"图片数据长度: {len(image_data_url)}")
    print(f"Prompt: {prompt[:50]}...")

    request = LLMRequest(messages=messages, tools=None)

    try:
        response = await llm_gateway.invoke(request)
        print(f"\n✅ LLM 调用完成!")
        print(f"  Success: {response.success}")
        print(f"  Error: {response.error}")
        if response.success and response.data:
            content = response.data.get("content", "")
            print(f"  Content: {content[:500] if content else '(空)'}...")
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    await test_llm_multimodal()


if __name__ == "__main__":
    asyncio.run(main())