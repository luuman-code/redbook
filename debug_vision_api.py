#!/usr/bin/env python3
"""
测试 Vision API 是否可访问
"""

import asyncio
import os
import sys
import json
import base64

# 添加项目根目录到 path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from agent.models.gateway_factory import GatewayFactory
from agent.config.config_service import AgentConfigService


def get_test_image_base64():
    """获取测试图片的 base64 编码"""
    # 创建一个简单的 100x100 蓝色 PNG 图片
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
    return base64.b64encode(png_bytes).decode('utf-8')


async def test_vision_api():
    """测试 Vision API"""
    config_service = AgentConfigService()

    # 获取 vision gateway
    vision_gateway = GatewayFactory.get_gateway("vision", config_service)

    # 检查配置
    print("=" * 60)
    print("Vision Gateway 配置:")
    print(f"  Provider: {type(vision_gateway._primary_provider).__name__}")
    print(f"  Model: {vision_gateway._primary_provider.model_name}")
    print(f"  API URL: {vision_gateway._primary_provider.api_url}")
    print(f"  API Key: {vision_gateway._primary_provider.api_key[:10]}...")
    print("=" * 60)

    # 获取测试图片
    image_base64 = get_test_image_base64()
    image_data_url = f"data:image/png;base64,{image_base64}"

    # 创建 Vision Request
    from agent.models.vision_gateway import VisionRequest
    request = VisionRequest(
        images=[image_data_url],
        prompt="请分析这张图片的内容"
    )

    print(f"\n发送 Vision API 请求...")
    print(f"  图片数据长度: {len(image_data_url)} 字符")
    print(f"  Prompt: {request.prompt}")

    try:
        response = await vision_gateway.invoke(request)
        print(f"\n✅ Vision API 调用完成!")
        print(f"  Success: {response.success}")
        print(f"  Error: {response.error}")
        print(f"  Data: {json.dumps(response.data, ensure_ascii=False, indent=2)[:500] if response.data else 'null'}...")
    except Exception as e:
        print(f"\n❌ Vision API 调用失败!")
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    await test_vision_api()


if __name__ == "__main__":
    asyncio.run(main())