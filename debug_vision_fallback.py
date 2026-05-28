#!/usr/bin/env python3
"""
测试 Vision API fallback 模型
"""

import asyncio
import os
import sys
import json
import base64

# 添加项目根目录到 path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from agent.config.config_service import AgentConfigService


async def test_vision_fallback():
    """测试 Vision API fallback 模型"""
    config_service = AgentConfigService()

    # 获取 vision fallback 配置
    fallback_config = config_service.get_provider_config("vision", "fallback")
    primary_config = config_service.get_provider_config("vision", "primary")

    print("=" * 60)
    print("Vision 模型配置:")
    print(f"  Primary: {primary_config.get('model_name')} (enabled: {primary_config.get('enabled')})")
    print(f"  Fallback: {fallback_config.get('model_name')} (enabled: {fallback_config.get('enabled')})")
    print("=" * 60)

    # 测试 wan2.7-image 模型
    import httpx

    # 获取 API key
    api_key = fallback_config.get('api_key')
    api_url = fallback_config.get('api_url')
    model_name = fallback_config.get('model_name')

    # 创建测试图片
    import zlib

    def create_png(width, height, color=(100, 150, 255)):
        def png_chunk(chunk_type, data):
            chunk = chunk_type + data
            crc = zlib.crc32(chunk) & 0xffffffff
            return len(data).to_bytes(4, 'big') + chunk + crc.to_bytes(4, 'big')

        png_data = b'\x89PNG\r\n\x1a\n'
        ihdr_data = width.to_bytes(4, 'big') + height.to_bytes(4, 'big')
        ihdr_data += b'\x08\x02\x00\x00\x00'
        png_data += png_chunk(b'IHDR', ihdr_data)

        raw_data = b''
        for y in range(height):
            raw_data += b'\x00'
            for x in range(width):
                raw_data += bytes(color)

        compressed = zlib.compress(raw_data, 9)
        png_data += png_chunk(b'IDAT', compressed)
        png_data += png_chunk(b'IEND', b'')

        return png_data

    png_bytes = create_png(100, 100)
    image_base64 = base64.b64encode(png_bytes).decode('utf-8')
    image_data_url = f"data:image/png;base64,{image_base64}"

    # 构建请求
    data = {
        "model": model_name,
        "input": {
            "messages": [{
                "role": "user",
                "content": [
                    {"image": image_data_url},
                    {"text": "请分析这张图片的内容"}
                ]
            }]
        },
        "parameters": {
            "size": "1K",
            "n": 1,
            "watermark": False
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"\n测试模型: {model_name}")
    print(f"API URL: {api_url}")
    print(f"图片数据长度: {len(image_data_url)}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(api_url, json=data, headers=headers)
            print(f"\n响应状态: {response.status_code}")
            print(f"响应内容: {response.text[:500]}")

            if response.status_code == 200:
                print("✅ 模型可用!")
            else:
                print(f"❌ 模型返回错误: {response.status_code}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")


async def main():
    await test_vision_fallback()


if __name__ == "__main__":
    asyncio.run(main())