#!/usr/bin/env python3
"""
测试 qwen-image-2.0-pro 图像编辑 API - 正确格式
"""

import asyncio
import os
import sys
import json
import base64
import zlib

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

import httpx


def create_test_png():
    """创建一个简单的测试 PNG"""
    def png_chunk(chunk_type, data):
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return len(data).to_bytes(4, 'big') + chunk + crc.to_bytes(4, 'big')

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


async def test_correct_format():
    """测试正确的 qwen-image-2.0-pro 图像编辑格式"""
    api_key = "sk-b8254f4363744ca3a265a27da530df66"
    api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    png_bytes = create_test_png()
    image_base64 = base64.b64encode(png_bytes).decode('utf-8')

    print("=" * 60)
    print("测试 qwen-image-2.0-pro 图像编辑 API")
    print("=" * 60)
    print(f"API URL: {api_url}")
    print(f"图片数据长度: {len(image_base64)}")

    # 正确的格式
    prompt = """请将这张小红书文案模板图片中的文字替换为新内容：
标题：今天的咖啡时光
正文：阳光正好，微风不燥
话题：#生活美学 #咖啡时光

要求：
1. 保持原有模板的布局和风格
2. 文字大小和位置与原图协调
3. 不要改变背景和装饰元素"""

    data = {
        "model": "qwen-image-2.0-pro",
        "input": {
            "messages": [{
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{image_base64}"},
                    {"text": prompt}
                ]
            }]
        },
        "parameters": {
            "n": 1,
            "prompt_extend": True,
            "watermark": False,
            "size": "2048*2048"
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"\nPrompt: {prompt[:100]}...")
    print(f"Parameters: n=1, prompt_extend=True, watermark=False, size=2048*2048")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(api_url, json=data, headers=headers)
            print(f"\n响应状态: {response.status_code}")
            print(f"响应: {response.text[:500]}...")

            if response.status_code == 200:
                result = response.json()
                print(f"\n✅ 成功!")
                print(json.dumps(result, ensure_ascii=False, indent=2)[:1000])

                # 检查返回的是图片还是文字
                choices = result.get("output", {}).get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", [])
                    for item in content:
                        if "text" in item:
                            print(f"\n📝 文本响应: {item['text'][:200]}...")
                        if "image" in item:
                            print(f"\n🖼️ 图片响应: {item['image'][:100]}...")
    except Exception as e:
        print(f"❌ 请求失败: {e}")


async def main():
    await test_correct_format()


if __name__ == "__main__":
    asyncio.run(main())