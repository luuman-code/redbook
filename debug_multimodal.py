#!/usr/bin/env python3
"""
调试脚本：检查 LLM 是否正确接收多模态内容并触发工具调用
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


# 读取一张测试图片并转为 base64
def get_test_image_base64():
    """获取测试图片的 base64 编码"""
    # 使用一个简单的红色方块图片作为测试
    # 这是最小的有效 PNG 图片 (1x1 红色像素)
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    return base64.b64encode(png_data).decode('utf-8')


# 系统提示词
SYSTEM_PROMPT = """你是一个专业的小红书内容创作助手，名字叫"小红书创作助手"。

## ⚠️ 重要：工具必须按顺序调用

### 工具调用规则

当你决定调用工具时，**必须按以下顺序执行**：

【第一步】analyze_template（分析图片）- **仅当用户发送图片时调用**
【第二步】modify_plan（生成方案）
【第三步】generate_template_preview（生成预览）

### 关键规则：自动继续 ⭐️

**【重要】收到工具结果后，你必须立即调用下一个工具！**

- 调用完 `analyze_template` 后，你**必须**调用 `modify_plan`
- 调用完 `modify_plan` 后，你**必须**调用 `generate_template_preview`
- 调用完 `generate_template_preview` 后，你**可以**回复用户

**【警告】完成所有工具调用前，不要回复用户！**
"""


# 工具定义
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_template",
            "description": "分析文案模板图片，提取文案结构、风格特点和格式特征。当用户上传了文案模板图片时使用此工具。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_plan",
            "description": "创建或修改内容方案。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_input": {"type": "string", "description": "用户的需求描述"},
                },
                "required": ["user_input"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_template_preview",
            "description": "生成文案模板预览图。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话 ID"},
                },
                "required": ["session_id"],
            }
        }
    },
]


async def test_multimodal():
    """测试多模态内容发送"""
    config_service = AgentConfigService()
    llm_gateway = GatewayFactory.get_gateway("llm", config_service)

    # 读取测试图片
    image_base64 = get_test_image_base64()

    # 构建多模态消息 (DashScope 格式)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"text": "我上传了一个文案模板图片，请帮我按照这个风格写一个露营内容，并生成预览。"},
                {"image": image_base64}
            ]
        }
    ]

    print("=" * 60)
    print("测试：发送多模态消息（文本+图片）给 LLM")
    print("=" * 60)
    print(f"消息结构:")
    print(f"  - system: {len(SYSTEM_PROMPT)} 字符")
    print(f"  - user content: 2 项 (text + image)")
    print(f"  - image size: {len(image_base64)} 字符 (base64)")
    print()

    from agent.models.llm_gateway import LLMRequest
    request = LLMRequest(messages=messages, tools=TOOLS)

    print("调用 LLM...")
    response = await llm_gateway.invoke(request)

    print()
    if response.success:
        print(f"✅ LLM 调用成功")
        print(f"  content: {response.data.get('content', '')[:200]}...")

        tool_calls = response.data.get('tool_calls')
        if tool_calls:
            print(f"  tool_calls: {len(tool_calls)} 个")
            for tc in tool_calls:
                print(f"    - {tc['function']['name']}")
        else:
            print(f"  tool_calls: 无")
    else:
        print(f"❌ LLM 调用失败: {response.error}")


async def test_text_only():
    """测试纯文本消息"""
    config_service = AgentConfigService()
    llm_gateway = GatewayFactory.get_gateway("llm", config_service)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "我上传了一个文案模板图片，请帮我按照这个风格写一个露营内容，并生成预览。"
        }
    ]

    print()
    print("=" * 60)
    print("测试：发送纯文本消息（无图片）给 LLM")
    print("=" * 60)

    from agent.models.llm_gateway import LLMRequest
    request = LLMRequest(messages=messages, tools=TOOLS)

    print("调用 LLM...")
    response = await llm_gateway.invoke(request)

    print()
    if response.success:
        print(f"✅ LLM 调用成功")
        print(f"  content: {response.data.get('content', '')[:200]}...")

        tool_calls = response.data.get('tool_calls')
        if tool_calls:
            print(f"  tool_calls: {len(tool_calls)} 个")
            for tc in tool_calls:
                print(f"    - {tc['function']['name']}")
        else:
            print(f"  tool_calls: 无")
    else:
        print(f"❌ LLM 调用失败: {response.error}")


async def main():
    await test_multimodal()
    await test_text_only()


if __name__ == "__main__":
    asyncio.run(main())