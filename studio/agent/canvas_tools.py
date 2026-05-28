"""
画板专用工具 - CanvasTools

这些工具专门用于画板（Canvas）操作，与 XiaohongshuAgent 的工具集完全独立。
"""

import asyncio
import json
import logging
import math
import uuid
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from mini_agent.tools.base import Tool

from ..core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

class CanvasToolResult:
    """画板工具执行结果"""

    def __init__(self, success: bool, content: str = "", error: str = "", warning: str = ""):
        self.success = success
        self.content = content
        self.error = error
        self.warning = warning


class CanvasUnderstandTool(Tool):
    """
    理解画板状态工具

    用于理解当前画布状态、选择内容和操作历史。
    仅用于理解，不执行任何修改。
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator):
        self.canvas = canvas_core
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "canvas_understand"

    @property
    def description(self) -> str:
        return """理解用户在画板上的操作意图和上下文。

当需要了解当前画布状态时使用此工具。

输入：
- operation: 当前操作信息（可选）
- selection_content: 框选/选中区域的内容（可选）
- history: 操作历史（可选）
- canvas_summary: 画板摘要

此工具仅用于理解当前状态，不会修改任何内容。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "object",
                    "description": "CanvasOperation，当前操作信息"
                },
                "selection_content": {
                    "type": "object",
                    "description": "框选/选中区域的内容"
                },
                "history": {
                    "type": "array",
                    "description": "操作历史"
                },
                "canvas_summary": {
                    "type": "object",
                    "description": "画板摘要信息"
                }
            },
            "required": []
        }

    async def execute(
        self,
        canvas_summary: Optional[Dict[str, Any]] = None,
        operation: Optional[Dict[str, Any]] = None,
        selection_content: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> CanvasToolResult:
        try:
            # 如果没有提供 canvas_summary，从 canvas_core 获取
            if canvas_summary is None:
                if self.canvas:
                    snapshot = self.canvas.get_snapshot()
                    canvas_summary = {
                        "canvas_id": self.canvas.canvas_id if self.canvas else "unknown",
                        "element_count": len(snapshot.elements) if snapshot else 0,
                        "elements": [elem.to_dict() for elem in snapshot.elements] if snapshot else [],
                    }
                else:
                    canvas_summary = {"canvas_id": "unknown", "element_count": 0, "elements": []}

            # 提取画板摘要信息
            canvas_id = canvas_summary.get("canvas_id", "unknown")
            element_count = canvas_summary.get("element_count", 0)
            elements = canvas_summary.get("elements", [])

            # 构建理解结果
            understanding = {
                "canvas_id": canvas_id,
                "element_count": element_count,
                "elements_summary": self._summarize_elements(elements),
                "selection_info": self._get_selection_info(selection_content),
                "operation_type": operation.get("type") if operation else None,
                "history_count": len(history) if history else 0,
            }

            return CanvasToolResult(
                success=True,
                content=json.dumps(understanding, ensure_ascii=False)
            )
        except Exception as e:
            logger.error(f"CanvasUnderstandTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"理解画板状态异常: {str(e)}")

    def _summarize_elements(self, elements: List[Dict]) -> Dict[str, Any]:
        """总结元素信息"""
        if not elements:
            return {"total": 0, "by_type": {}}

        by_type: Dict[str, int] = {}
        for elem in elements:
            elem_type = elem.get("type", "unknown")
            by_type[elem_type] = by_type.get(elem_type, 0) + 1

        return {
            "total": len(elements),
            "by_type": by_type,
        }

    def _get_selection_info(self, selection_content: Optional[Dict]) -> Dict[str, Any]:
        """获取选中区域信息"""
        if not selection_content:
            return {"has_selection": False}

        return {
            "has_selection": True,
            "element_count": len(selection_content.get("element_ids", [])),
            "bounds": selection_content.get("bounds", {}),
        }


class CanvasSuggestTool(Tool):
    """
    画板创意建议工具

    基于当前画板状态生成创意建议。
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator):
        self.canvas = canvas_core
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "canvas_suggest"

    @property
    def description(self) -> str:
        return """基于当前画板状态生成创意建议。

当用户明确要求提供建议时使用此工具。

注意：只有在用户明确要求时才能调用此工具。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self) -> CanvasToolResult:
        try:
            snapshot = self.canvas.get_snapshot()

            # 分析当前画板状态
            elements = snapshot.elements
            if not elements:
                suggestions = [
                    "画板目前是空的，可以考虑添加一些元素",
                    "可以从添加文本标题开始创作",
                ]
            else:
                suggestions = [
                    "当前画板已有内容，创作空间充足",
                    "可以考虑调整元素之间的对齐关系",
                    "颜色搭配可以更加丰富",
                ]

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "suggestions": suggestions,
                    "element_count": len(elements),
                }, ensure_ascii=False)
            )
        except Exception as e:
            logger.error(f"CanvasSuggestTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"生成建议异常: {str(e)}")


class CanvasGenerateTool(Tool):
    """
    画板内容生成工具

    在画板上生成新内容（文本/图片/视频/音频）。
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator):
        self.canvas = canvas_core
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "canvas_generate"

    @property
    def description(self) -> str:
        return """在画板上生成新内容（文本/图片/视频/音频）。

当用户明确要求生成新内容时使用此工具。

输入：
- target_region: 目标区域（框选区域/元素ID）
- generate_type: 生成类型 (text/image/video/audio)

规则：
- 在用户指定位置生成，不要随意放置
- 如果没有指定位置，先询问用户
- 遵循用户的生成指令"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target_region": {
                    "type": "object",
                    "description": "目标区域（框选区域/元素ID）"
                },
                "generate_type": {
                    "type": "string",
                    "enum": ["text", "image", "video", "audio"],
                    "description": "生成类型"
                },
                "params": {
                    "type": "object",
                    "description": "生成参数（可选）"
                }
            },
            "required": ["generate_type"]
        }

    async def execute(
        self,
        generate_type: str,
        target_region: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> CanvasToolResult:
        try:
            from ..canvas.canvas_core import CanvasElement, ElementMetadata, CreatorType

            # 如果没有指定位置，生成在画板中心
            if target_region:
                position = target_region.get("position", {"x": 100, "y": 100})
            else:
                position = {"x": 100, "y": 100}

            # 创建新元素
            element_id = self.canvas._generate_id()

            # 构建元素元数据
            metadata = ElementMetadata()
            if generate_type == "text":
                metadata.text_content = params.get("content", "新文本") if params else "新文本"
                metadata.font_size = params.get("font_size", 16) if params else 16
            elif generate_type == "image":
                metadata.url = params.get("url") if params else None
            elif generate_type == "video":
                metadata.url = params.get("url") if params else None
                metadata.duration = params.get("duration", 0) if params else 0

            # 创建元素
            element = CanvasElement(
                id=element_id,
                type=generate_type,
                position=position,
                size={"width": 200, "height": 100},
                metadata=metadata,
                created_by=CreatorType.AGENT.value,
            )

            # 添加到画板
            success = await self.canvas.add_element(element)

            if success:
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({
                        "element_id": element_id,
                        "type": generate_type,
                        "position": position,
                        "message": f"已生成新的{generate_type}元素"
                    }, ensure_ascii=False)
                )
            else:
                return CanvasToolResult(success=False, error="生成元素失败")
        except Exception as e:
            logger.error(f"CanvasGenerateTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"生成内容异常: {str(e)}")


class CanvasEditTool(Tool):
    """
    画板元素编辑工具

    编辑画板上现有的元素。
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator):
        self.canvas = canvas_core
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "canvas_edit"

    @property
    def description(self) -> str:
        return """编辑画板上现有的元素。

当用户框选/选中内容 + 明确描述修改需求时使用。

【重要】使用此工具前，请先激活 canvas_edit 技能获取完整的使用指南。
激活技能：use_skill("canvas_edit")"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "element_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要编辑的元素ID列表"
                },
                "edit_instruction": {
                    "type": "string",
                    "description": "用户对选中内容的修改描述"
                }
            },
            "required": ["element_ids", "edit_instruction"]
        }

    async def execute(
        self,
        element_ids: List[str],
        edit_instruction: str,
    ) -> CanvasToolResult:
        try:
            # 解析编辑指令
            edits = self._parse_edit_instruction(edit_instruction)

            # 执行更新
            affected_ids = []
            for element_id in element_ids:
                success = await self.canvas.update_element(element_id, edits)
                if success:
                    affected_ids.append(element_id)

            if affected_ids:
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({
                        "affected_ids": affected_ids,
                        "edits": edits,
                        "message": f"已修改 {len(affected_ids)} 个元素"
                    }, ensure_ascii=False)
                )
            else:
                return CanvasToolResult(success=False, error="没有元素被修改")
        except Exception as e:
            logger.error(f"CanvasEditTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"编辑元素异常: {str(e)}")

    def _parse_edit_instruction(self, instruction: str) -> Dict[str, Any]:
        """解析编辑指令

        注意：根据新的提示词模板，edit_instruction 现在直接就是新文本内容，
        不再需要从复杂格式中提取。
        """
        edits: Dict[str, Any] = {}
        import re

        instruction_lower = instruction.lower()

        # 解析文本内容 - edit_instruction 现在直接就是新文本内容
        # 只需要清理末尾可能的标点符号
        if instruction:
            new_text = instruction.strip()
            # 清理末尾的标点符号
            new_text = re.sub(r'[,，。.!?！？"\']+$', '', new_text)
            if new_text:
                edits["metadata"] = {"text_content": new_text}

        # 解析样式修改（这些仍然可能通过特殊指令触发）
        if "颜色" in instruction or "color" in instruction_lower:
            if "红色" in instruction:
                edits.setdefault("styles", {})["color"] = "#FF0000"
            elif "蓝色" in instruction:
                edits.setdefault("styles", {})["color"] = "#0000FF"
            elif "绿色" in instruction:
                edits.setdefault("styles", {})["color"] = "#00FF00"

        # 解析大小修改
        if "放大" in instruction:
            edits["size_increase"] = 1.2
        elif "缩小" in instruction:
            edits["size_increase"] = 0.8

        return edits


class CanvasOperateTool(Tool):
    """
    画板操作工具

    执行画板操作（移动/缩放/对齐等）。
    """

    def __init__(self, canvas_core):
        self.canvas = canvas_core

    @property
    def name(self) -> str:
        return "canvas_operate"

    @property
    def description(self) -> str:
        return """执行画板操作（移动/缩放/对齐等）。

当用户明确要求执行特定操作时使用。

支持的操类型：
- move: 移动元素
- resize: 缩放元素
- rotate: 旋转元素
- align: 对齐元素
- group: 组合元素
- ungroup: 取消组合"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation_type": {
                    "type": "string",
                    "enum": ["move", "resize", "rotate", "align", "group", "ungroup"],
                    "description": "操作类型"
                },
                "element_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "目标元素ID列表"
                },
                "params": {
                    "type": "object",
                    "description": "操作参数"
                }
            },
            "required": ["operation_type", "element_ids"]
        }

    async def execute(
        self,
        operation_type: str,
        element_ids: List[str],
        params: Optional[Dict[str, Any]] = None,
    ) -> CanvasToolResult:
        try:
            from ..canvas.canvas_core import CanvasOperation, OperationType

            params = params or {}

            # 创建操作
            op = CanvasOperation(
                id=self.canvas._generate_id(),
                type=operation_type,
                target_ids=element_ids,
                after_state=params,
                creator="agent",
            )

            # 执行操作
            result = await self.canvas.execute_operation(op)

            if result.success:
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({
                        "operation_id": op.id,
                        "affected_ids": result.affected_ids,
                        "message": f"已执行{operation_type}操作"
                    }, ensure_ascii=False)
                )
            else:
                return CanvasToolResult(success=False, error=result.error or "操作失败")
        except Exception as e:
            logger.error(f"CanvasOperateTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"执行操作异常: {str(e)}")


class CanvasGlobalEditTool(Tool):
    """
    画板全局编辑工具

    对整个画布内容进行全局修改。
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator):
        self.canvas = canvas_core
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "canvas_global_edit"

    @property
    def description(self) -> str:
        return """对整个画布内容进行全局修改。

当用户未选择内容 + 明确描述全局修改需求时使用。

输入：
- canvas_id: 画板ID
- instruction: 用户的全局修改描述

规则：
- 只执行用户明确要求的修改
- 全局修改影响所有相关元素"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "canvas_id": {
                    "type": "string",
                    "description": "画板ID"
                },
                "instruction": {
                    "type": "string",
                    "description": "用户的全局修改描述"
                }
            },
            "required": ["canvas_id", "instruction"]
        }

    async def execute(
        self,
        canvas_id: str,
        instruction: str,
    ) -> CanvasToolResult:
        try:
            # 验证 canvas_id
            if canvas_id != self.canvas.canvas_id:
                return CanvasToolResult(success=False, error="画板ID不匹配")

            # 获取所有元素
            elements = self.canvas.elements

            # 解析全局修改指令
            global_edits = self._parse_global_instruction(instruction)

            # 执行全局修改
            affected_ids = []
            for element in elements:
                success = await self.canvas.update_element(element.id, global_edits)
                if success:
                    affected_ids.append(element.id)

            if affected_ids:
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({
                        "affected_count": len(affected_ids),
                        "edits": global_edits,
                        "message": f"已对 {len(affected_ids)} 个元素执行全局修改"
                    }, ensure_ascii=False)
                )
            else:
                return CanvasToolResult(success=False, error="没有元素被修改")
        except Exception as e:
            logger.error(f"CanvasGlobalEditTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"全局修改异常: {str(e)}")

    def _parse_global_instruction(self, instruction: str) -> Dict[str, Any]:
        """解析全局修改指令"""
        edits: Dict[str, Any] = {}

        instruction_lower = instruction.lower()

        # 解析全局样式修改
        if "统一颜色" in instruction or "全部变" in instruction:
            if "红色" in instruction:
                edits["styles"] = {"color": "#FF0000"}
            elif "蓝色" in instruction:
                edits["styles"] = {"color": "#0000FF"}
            elif "黑色" in instruction:
                edits["styles"] = {"color": "#000000"}

        if "放大" in instruction:
            edits["size_scale"] = 1.2
        elif "缩小" in instruction:
            edits["size_scale"] = 0.8

        return edits


class CanvasImageEditTool(Tool):
    """
    画板图片编辑工具

    使用 AI 模型编辑图片内容，如修改图片中的文字、风格等。
    支持本地图片和 URL 图片。
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator):
        self.canvas = canvas_core
        self.orchestrator = orchestrator
        self._vision_gateway = None
        self._http_client = None

    def _get_http_client(self):
        """获取 HTTP 客户端"""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=120.0)
        return self._http_client

    async def _ensure_public_url(self, image_url: str) -> str:
        """
        确保图片 URL 是公开可访问的

        如果是 data:image URL，提取 base64 数据并上传到 OSS 返回公开 URL
        如果是 blob URL，返回原始 URL（前端会处理）

        Args:
            image_url: 原始图片 URL (可能是 blob: 或 data:image:)

        Returns:
            公开可访问的 URL
        """
        # 如果已经是 http/https URL，直接返回
        if image_url.startswith("http://") or image_url.startswith("https://"):
            return image_url

        # 如果是 data:image: URL，提取 base64 数据并上传到 OSS
        if image_url.startswith("data:image:"):
            logger.info(f"[CanvasImageEdit] 检测到 data:image URL，开始上传到 OSS")

            try:
                # 提取 base64 数据
                # 格式: data:image/png;base64,iVBORw0KG...
                parts = image_url.split(",", 1)
                if len(parts) != 2:
                    raise Exception(f"无效的 data:image URL 格式")

                header = parts[0]  # data:image/png;base64
                base64_data = parts[1]

                # 从 header 中提取 MIME 类型
                mime_type = "image/png"
                if "image/" in header:
                    mime_part = header.split(";")[0]
                    if "/" in mime_part:
                        mime_type = mime_part.split("/")[1]
                        if mime_type == "jpeg":
                            mime_type = "jpg"

                # 解码 base64
                import base64
                image_data = base64.b64decode(base64_data)

                # 上传到 OSS
                import sys
                from pathlib import Path
                # 将项目根目录添加到 sys.path
                project_root = Path(__file__).parent.parent.parent
                if str(project_root) not in sys.path:
                    sys.path.insert(0, str(project_root))

                from agent.config.config_service import AgentConfigService
                config_service = AgentConfigService()
                env_config = config_service.get_environment_config()
                oss_config = env_config.get("oss", {})

                if not oss_config or not oss_config.get("access_key_id"):
                    raise Exception("OSS 配置未找到")

                import oss2
                import uuid

                ext = mime_type if mime_type != "jpeg" else "jpg"
                filename = f"{uuid.uuid4().hex[:16]}.{ext}"

                access_key_id = oss_config["access_key_id"]
                access_key_secret = oss_config["access_key_secret"]
                bucket_name = oss_config["bucket"]
                endpoint = oss_config["endpoint"]

                auth = oss2.Auth(access_key_id, access_key_secret)
                bucket = oss2.Bucket(auth, endpoint, bucket_name)

                result = bucket.put_object(filename, image_data)
                if result.status != 200:
                    raise Exception(f"OSS 上传失败: status={result.status}")

                public_url = f"https://{bucket_name}.{endpoint}/{filename}"
                logger.info(f"[CanvasImageEdit] 上传到 OSS 成功: {public_url}")
                return public_url

            except Exception as e:
                logger.error(f"[CanvasImageEdit] OSS 上传失败: {e}")
                raise Exception(f"图片上传到 OSS 失败: {e}")

        # 如果是 blob: URL，服务器无法访问，返回错误提示
        if image_url.startswith("blob:"):
            raise Exception("blob URL 无法被服务器访问，请使用前端上传功能将图片上传到服务器")

        # 其他格式的 URL，直接返回
        return image_url

    @property
    def name(self) -> str:
        return "canvas_image_edit"

    @property
    def description(self) -> str:
        return """使用 AI 编辑图片内容。

当用户选中图片并要求修改图片内的文字、风格、元素等时使用。

输入：
- element_ids: 要编辑的图片元素ID列表
- edit_instruction: 对图片的修改描述，如"将文字改成 hello world"、"添加水印"等

支持：
- 修改图片中的文字内容
- 调整图片风格
- 添加/移除元素
- 图片润色和优化

注意：
- 仅适用于 image 类型元素
- 需要图片有有效的 URL 或 local_path
- 编辑结果会替换原图片"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "element_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要编辑的图片元素ID列表"
                },
                "edit_instruction": {
                    "type": "string",
                    "description": "对图片的修改描述，如'将文字改成 hello world'"
                }
            },
            "required": ["element_ids", "edit_instruction"]
        }

    async def execute(
        self,
        element_ids: List[str],
        edit_instruction: str,
    ) -> CanvasToolResult:
        """执行图片编辑"""
        try:
            logger.info(f"[CanvasImageEdit] execute called with element_ids={element_ids}, edit_instruction={edit_instruction[:50]}...")

            # 收集图片信息
            images_to_edit = []
            valid_element_ids = []

            for element_id in element_ids:
                element = self.canvas.get_element(element_id)
                if not element:
                    logger.warning(f"元素 {element_id} 不存在")
                    continue

                if element.type != "image":
                    logger.warning(f"元素 {element_id} 不是图片类型")
                    continue

                # 获取图片 URL
                image_url = element.metadata.url or element.metadata.local_path
                if not image_url:
                    logger.warning(f"元素 {element_id} 没有有效的图片路径")
                    continue

                logger.info(f"[CanvasImageEdit] element_id={element_id}, image_url={image_url[:50] if image_url else 'None'}...")

                images_to_edit.append({
                    "element_id": element_id,
                    "url": image_url,
                    "element": element
                })
                valid_element_ids.append(element_id)

            if not images_to_edit:
                return CanvasToolResult(
                    success=False,
                    error="没有有效的图片可供编辑"
                )

            # 调用 Image Gateway 进行图片编辑
            image_url = images_to_edit[0]["url"]  # 当前只支持单张图片编辑

            logger.info(f"[CanvasImageEdit] 开始处理图片: {image_url[:50] if image_url else 'None'}...")

            # 确保图片 URL 是公开可访问的（如果是 blob 或 data:image，需要先上传到 OSS）
            try:
                image_url = await self._ensure_public_url(image_url)
            except Exception as e:
                return CanvasToolResult(
                    success=False,
                    error=f"图片上传失败: {str(e)}"
                )

            logger.info(f"[CanvasImageEdit] 公开 URL: {image_url}")
            logger.info(f"[CanvasImageEdit] 编辑指令: {edit_instruction}")

            # 直接调用图片编辑 API
            import httpx

            # 获取 API 配置
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            from agent.config.config_service import AgentConfigService
            config_service = AgentConfigService()
            # 从 image_generation 模型的配置中获取 API key
            image_gen_config = config_service.get_model_config("image_generation")
            api_key = image_gen_config.get("primary", {}).get("api_key") or image_gen_config.get("fallback", {}).get("api_key")
            api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            model_name = "qwen-image-2.0-pro"  # 图片编辑模型

            if not api_key:
                return CanvasToolResult(
                    success=False,
                    error="未配置图片编辑 API Key"
                )

            # 构建请求 - 使用 multimodal-generation API 格式
            data = {
                "model": model_name,
                "input": {
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"image": image_url},
                            {"text": f"请根据以下指令编辑图片：{edit_instruction}"}
                        ]
                    }]
                }
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(api_url, json=data, headers=headers)

                    if response.status_code != 200:
                        return CanvasToolResult(
                            success=False,
                            error=f"图片编辑 API 错误: {response.status_code} - {response.text}"
                        )

                    result = response.json()
            except Exception as e:
                return CanvasToolResult(
                    success=False,
                    error=f"图片编辑请求失败: {str(e)}"
                )

            # 解析编辑结果
            edited_images = []
            logger.info(f"[CanvasImageEdit] API 返回结果: {result}")
            if "output" in result and "choices" in result["output"]:
                for choice in result["output"]["choices"]:
                    if "message" in choice and "content" in choice["message"]:
                        for item in choice["message"]["content"]:
                            # 支持 "image_url" 或 "image" 两种 key
                            image_url = item.get("image_url") or item.get("image")
                            if image_url:
                                edited_images.append({"url": image_url})

            # 更新画布元素
            updated_elements = []
            logger.info(f"[CanvasImageEdit] 解析出 {len(edited_images)} 个编辑结果，images_to_edit 长度为 {len(images_to_edit)}")
            for i, edited_image in enumerate(edited_images):
                if i >= len(images_to_edit):
                    break

                new_url = edited_image.get("url")
                if not new_url:
                    continue

                element_id = images_to_edit[i]["element_id"]

                # 更新元素的 URL
                logger.info(f"[CanvasImageEdit] 正在更新元素 {element_id} 的 URL 为 {new_url}")
                success = await self.canvas.update_element(
                    element_id,
                    {"metadata": {"url": new_url}}
                )
                logger.info(f"[CanvasImageEdit] 更新元素结果: success={success}")

                if success:
                    updated_elements.append({
                        "element_id": element_id,
                        "new_url": new_url
                    })
                    logger.info(f"[CanvasImageEdit] 已更新元素 {element_id} 的图片")

            if updated_elements:
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({
                        "updated_count": len(updated_elements),
                        "updated_elements": updated_elements,
                        "message": f"已编辑 {len(updated_elements)} 张图片"
                    }, ensure_ascii=False)
                )
            else:
                return CanvasToolResult(
                    success=False,
                    error="图片编辑成功但未能更新元素"
                )

        except Exception as e:
            logger.error(f"CanvasImageEditTool exception: {e}", exc_info=True)
            return CanvasToolResult(
                success=False,
                error=f"图片编辑异常: {str(e)}"
            )

    def _get_image_gateway(self):
        """获取 Image Gateway 实例"""
        # 直接使用 orchestrator 的 image_gateway
        if hasattr(self.orchestrator, 'image_gateway'):
            return self.orchestrator.image_gateway
        return None


class WebSocketProgressCallback:
    """WebSocket 进度回调，用于流式绘画"""

    def __init__(self, canvas_id: str):
        self.canvas_id = canvas_id

    async def send_progress(self, element_id: str, points: List[List[float]],
                          done: bool, stroke_color: str = "#000000",
                          stroke_width: float = 2, x: float = 0, y: float = 0,
                          fill_color: str = "#000000"):
        """发送绘画进度"""
        from ..api.canvas_routes import broadcast_to_canvas

        message = {
            "type": "DRAW_PROGRESS",
            "item_id": element_id,
            "data": {
                "item_id": element_id,
                "points": points,
                "stroke_color": stroke_color,
                "stroke_width": stroke_width,
                "fill_color": fill_color,
                "done": done,
                "x": x,
                "y": y
            }
        }
        await broadcast_to_canvas(self.canvas_id, message)

    async def send_start(self, element_id: str, draw_type: str):
        """发送开始绘制事件"""
        from ..api.canvas_routes import broadcast_to_canvas

        message = {
            "type": "DRAW_START",
            "item_id": element_id,
            "data": {
                "item_id": element_id,
                "item_type": draw_type
            }
        }
        await broadcast_to_canvas(self.canvas_id, message)

    async def send_complete(self, element_id: str, element_data: dict):
        """发送完成绘制事件"""
        from ..api.canvas_routes import broadcast_to_canvas

        # DEBUG: 检查发送的元素数据
        logger.info(f"[DEBUG send_complete] element_id={element_id}")
        logger.info(f"[DEBUG send_complete] element_data.metadata.fill_color={element_data.get('metadata', {}).get('fill_color')}")
        logger.info(f"[DEBUG send_complete] element_data.metadata.stroke_color={element_data.get('metadata', {}).get('stroke_color')}")
        logger.info(f"[DEBUG send_complete] element_data.metadata.points={element_data.get('metadata', {}).get('points')}")
        logger.info(f"[DEBUG send_complete] element_data.metadata.shape_type={element_data.get('metadata', {}).get('shape_type')}")
        logger.info(f"[DEBUG send_complete] element_data.styles.fill={element_data.get('styles', {}).get('fill')}")
        logger.info(f"[DEBUG send_complete] element_data.styles.stroke={element_data.get('styles', {}).get('stroke')}")

        message = {
            "type": "DRAW_COMPLETE",
            "item_id": element_id,
            "data": {
                "item_id": element_id,
                "element": element_data
            }
        }
        await broadcast_to_canvas(self.canvas_id, message)


class CanvasDrawTool(Tool):
    """画板绘画工具 - 在用户指定的框选区域内执行绘画操作"""

    # 类级别变量：最近绘制元素的最大数量
    MAX_RECENT_ELEMENTS = 5

    def __init__(self, canvas_core, orchestrator: Optional[Any] = None,
                 session_id: str = None, tool_result_store=None):
        self.canvas = canvas_core
        self.orchestrator = orchestrator
        self.session_id = session_id
        self.progress_callback = None
        # 最近绘制的元素列表（用于 Agent 智能定位下一步）
        self._recent_elements: List[Dict[str, Any]] = []
        # 取消事件引用（通过 session_id 获取）
        self._cancellation_event = None
        # 工具结果存储（用于跨调用获取历史绘制结果）
        self._tool_result_store = tool_result_store
        # 【新增】绘图会话计数器和锁
        self._drawing_session_count: int = 0  # 初始为0，表示新会话
        self._current_drawing_session_id: Optional[str] = None
        self._drawing_session_lock: asyncio.Lock = asyncio.Lock()  # 并发保护锁
        # 【新增】按 session_id 分组存储元素 ID
        self._session_element_ids: Dict[str, List[str]] = {}  # session_id -> element_ids

    @property
    def name(self) -> str:
        return "canvas_draw"

    @property
    def description(self) -> str:
        return """在画板指定区域执行 SVG Path 自由曲线绘制。

通过 path_data 参数传入 SVG path 命令。
operation 固定为 "brush"。

【重要】使用此工具前，请先激活 canvas_draw 技能获取完整的 SVG Path 使用指南。
激活技能：use_skill("canvas_draw")"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["brush"],
                    "description": "绘画操作（固定为 brush）"
                },
                "params": {
                    "type": "object",
                    "description": "path_data: SVG path command string; color: stroke color; stroke_width: line width; fill_color: fill color (optional); drawing_session_id: 绘图会话ID（可选，用于修改已有图案，传入后该图案的后续绘制会关联到此ID）"
                }
            },
            "required": ["operation"]
        }

    async def execute(
        self,
        operation: str,
        params: Optional[Dict[str, Any]] = None
    ) -> CanvasToolResult:
        """执行绘画 - 使用流式输出"""
        # 调试日志：确认 self.canvas 的值
        import os
        debug_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "logs", "execute_debug.log")
        with open(debug_path, "a", encoding="utf-8") as f:
            f.write(f"[EXECUTE] 方法被调用! self.canvas={self.canvas}, operation={operation}\n")
        if self.canvas:
            return await self.execute_streaming(operation, params)

        # 否则使用原有逻辑（兼容无 session_id 的情况）
        try:
            from ..canvas.canvas_core import CanvasElement, ElementMetadata, ElementStyles, ElementType

            # 从 canvas context 获取当前 selection bounds
            selection_bounds = self._get_current_selection_bounds()
            if not selection_bounds:
                return CanvasToolResult(
                    success=False,
                    error="请先使用框选工具选择区域"
                )

            params = params or {}
            stroke_color = params.get("color", "#000000")
            stroke_width = params.get("stroke_width", 2)
            fill_color = params.get("fill_color") or stroke_color  # 如果没有 fill_color，使用 stroke_color
            points = params.get("points", [])

            # 确保颜色是有效的十六进制格式（兼容颜色名称）
            def ensure_hex_color(color: str) -> str:
                """将颜色名称转换为十六进制格式"""
                color_map = {
                    "red": "#FF0000",
                    "green": "#00FF00",
                    "blue": "#0000FF",
                    "yellow": "#FFFF00",
                    "orange": "#FFA500",
                    "purple": "#800080",
                    "pink": "#FFC0CB",
                    "black": "#000000",
                    "white": "#FFFFFF",
                    "gray": "#808080",
                    "grey": "#808080",
                }
                color_lower = color.lower() if isinstance(color, str) else color
                return color_map.get(color_lower, color)  # 如果不是已知颜色名称，返回原值

            stroke_color = ensure_hex_color(stroke_color)
            fill_color = ensure_hex_color(fill_color)

            # 创建绘画元素（brush 操作使用 path）
            element = CanvasElement(
                id=str(uuid.uuid4()),
                type=ElementType.SHAPE.value,
                position={"x": actual_element_x, "y": actual_element_y},
                size={"width": actual_element_w, "height": actual_element_h},
                metadata=ElementMetadata(
                    shape_type="path",
                    points=points,
                    stroke_color=stroke_color,
                    stroke_width=stroke_width,
                    fill_color=fill_color
                ),
                styles=ElementStyles(
                    x=actual_element_x,
                    y=actual_element_y,
                    width=actual_element_w,
                    height=actual_element_h,
                    stroke=stroke_color,
                    stroke_width=stroke_width,
                    fill=fill_color if fill_color != stroke_color else None  # 只有明确指定填充色时才填充
                ),
                created_by="agent"
            )

            # 添加到画板
            success = await self.canvas.add_element(element)

            if success:
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({
                        "element_id": element.id,
                        "operation": operation,
                        "bounds": selection_bounds
                    }, ensure_ascii=False)
                )
            else:
                return CanvasToolResult(success=False, error="添加元素失败")

        except Exception as e:
            logger.error(f"CanvasDrawTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"绘制异常: {str(e)}")

    def _get_current_selection_bounds(self) -> Optional[Dict[str, float]]:
        """获取当前框选区域"""
        if hasattr(self.canvas, '_current_selection') and self.canvas._current_selection:
            selection = self.canvas._current_selection
            return selection.bounds
        return None

    def _ensure_progress_callback(self):
        """确保进度回调已初始化"""
        if self.progress_callback is None and self.canvas:
            self.progress_callback = WebSocketProgressCallback(
                self.canvas.canvas_id
            )

    def _get_cancellation_event(self):
        """获取取消事件"""
        if self._cancellation_event is not None:
            return self._cancellation_event

        # 尝试从 canvas_routes 获取取消事件
        if self.canvas and self.canvas.canvas_id:
            try:
                from studio.api.canvas_routes import get_cancellation_event
                return get_cancellation_event(self.canvas.canvas_id)
            except Exception:
                pass

        return None

    def _is_cancelled(self) -> bool:
        """检查是否已取消"""
        event = self._get_cancellation_event()
        if event and event.is_set():
            return True
        return False

    def _validate_bounds(
        self,
        draw_bounds: Dict[str, float],
        selection_bounds: Dict[str, float]
    ) -> tuple[bool, str]:
        """
        验证绘制的边界是否在选择区域内。

        Args:
            draw_bounds: 计算出的绘制边界
            selection_bounds: 用户框选的区域

        Returns:
            tuple: (is_valid, warning_message)
            - is_valid: True 如果边界有效
            - warning_message: 如果无效，返回警告消息
        """
        sel_x_start = selection_bounds["x"]
        sel_y_start = selection_bounds["y"]
        sel_x_end = sel_x_start + selection_bounds["width"]
        sel_y_end = sel_y_start + selection_bounds["height"]

        draw_x = draw_bounds["x"]
        draw_y = draw_bounds["y"]
        draw_width = draw_bounds.get("width", 0)
        draw_height = draw_bounds.get("height", 0)
        draw_x_end = draw_x + draw_width
        draw_y_end = draw_y + draw_height

        # 检查是否超出边界
        exceeds_left = draw_x < sel_x_start
        exceeds_top = draw_y < sel_y_start
        exceeds_right = draw_x_end > sel_x_end
        exceeds_bottom = draw_y_end > sel_y_end

        if exceeds_left or exceeds_top or exceeds_right or exceeds_bottom:
            # 生成详细的警告消息
            warning_parts = []
            if exceeds_left:
                warning_parts.append(f"左边超出 {sel_x_start - draw_x:.1f}px")
            if exceeds_top:
                warning_parts.append(f"上边超出 {sel_y_start - draw_y:.1f}px")
            if exceeds_right:
                warning_parts.append(f"右边超出 {draw_x_end - sel_x_end:.1f}px")
            if exceeds_bottom:
                warning_parts.append(f"下边超出 {draw_y_end - sel_y_end:.1f}px")

            warning_msg = (
                f"【Bounds检查失败】绘制的图形超出选择区域！\n"
                f"图形边界: x={draw_x:.1f}~{draw_x_end:.1f}, y={draw_y:.1f}~{draw_y_end:.1f}\n"
                f"选择区域: x={sel_x_start:.1f}~{sel_x_end:.1f}, y={sel_y_start:.1f}~{sel_y_end:.1f}\n"
                f"超出部分: {', '.join(warning_parts)}\n"
                f"\n"
                f"建议调整:\n"
                f"- 减小 scale 参数（当前 scale 导致图形过大）\n"
                f"- 或减小 offset_x/offset_y 偏移值\n"
                f"- 或使用 fit_below/fit_above 等自动适应模式\n"
                f"\n"
                f"请调整参数后重试。"
            )
            return False, warning_msg

        # 额外检查：bounds 是否合理（防止计算错误）
        is_reasonable = (
            -10000 < draw_x < 20000 and
            -10000 < draw_y < 20000 and
            0 < draw_width < 5000 and
            0 < draw_height < 5000
        )

        if not is_reasonable:
            warning_msg = (
                f"【Bounds检查失败】计算出的边界不合理！\n"
                f"图形边界: x={draw_x:.1f}, y={draw_y:.1f}, width={draw_width:.1f}, height={draw_height:.1f}\n"
                f"这可能是由于 scale 或 offset 参数设置不当导致的。\n"
                f"\n"
                f"请检查:\n"
                f"- scale 是否在 0.1-1.0 范围内？\n"
                f"- offset_x/offset_y 是否过大？\n"
                f"\n"
                f"请调整参数后重试。"
            )
            return False, warning_msg

        return True, ""

    def _calculate_relative_position(
        self,
        selection_bounds: Dict[str, float],
        params: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        计算相对定位。

        如果指定了 reference_element_id 和 relative_position，
        则基于参考元素的位置计算新的绘制区域。

        支持的相对位置：
        - above: 在参考元素上方
        - below: 在参考元素下方
        - left_of: 在参考元素左侧
        - right_of: 在参考元素右侧
        - centered_on: 中心对齐参考元素

        Args:
            selection_bounds: 用户框选的区域
            params: 绘画参数

        Returns:
            计算后的绘制区域
        """
        reference_element_id = params.get("reference_element_id")
        relative_position = params.get("relative_position")

        # 如果没有指定参考元素和相对位置，使用原始 selection_bounds
        if not reference_element_id or not relative_position:
            return selection_bounds

        # 查找参考元素
        reference_bounds = None
        for elem in self._recent_elements:
            if elem.get("element_id") == reference_element_id:
                reference_bounds = elem.get("bounds")
                break

        # 如果找不到参考元素，尝试使用最近的有效元素
        if not reference_bounds:
            logger.warning(
                f"Reference element {reference_element_id} not found in recent_elements, "
                f"using last valid element if available"
            )
            # 尝试使用 recent_elements 中最后一个元素
            if self._recent_elements:
                last_elem = self._recent_elements[-1]
                reference_bounds = last_elem.get("bounds")
                logger.info(f"Using last valid element: {last_elem.get('element_id')}")
            else:
                # 如果没有任何参考元素，使用 selection_bounds
                return selection_bounds

        # 获取 scale 和 offset
        scale = params.get("scale", 1.0)
        offset_x = params.get("offset_x", 0.0)
        offset_y = params.get("offset_y", 0.0)

        # 先计算缩放后的尺寸（后续计算会用到）
        # 基础相对定位模式（above/below/left_of/right_of/centered_on）使用参考元素的尺寸进行缩放
        # fit 系列模式（fit_below/fit_above）使用选择区域的尺寸进行缩放
        ref_width = reference_bounds["width"]
        ref_height = reference_bounds["height"]
        scaled_width = ref_width * scale
        scaled_height = ref_height * scale

        # 调试日志
        logger.info(f"[DEBUG _calculate_relative_position] scale={scale}, offset_x={offset_x}, offset_y={offset_y}")
        logger.info(f"[DEBUG _calculate_relative_position] reference_bounds={reference_bounds}")
        logger.info(f"[DEBUG _calculate_relative_position] scaled_width={scaled_width}, scaled_height={scaled_height}")

        # 参考元素的中心点
        ref_cx = reference_bounds["x"] + reference_bounds["width"] / 2
        ref_cy = reference_bounds["y"] + reference_bounds["height"] / 2

        # 基于参考元素计算新的中心位置
        # offset_x/offset_y 直接作为像素偏移值使用
        # 对于 above/below：offset_y > 0 表示向上偏移，offset_y < 0 表示向下偏移
        # 对于 left_of/right_of：offset_x > 0 表示向左偏移，offset_x < 0 表示向右偏移

        # 定位模式的说明：
        # - above/below/left_of/right_of/centered_on: 使用参考元素的尺寸进行缩放
        # - fit_below: 紧贴参考元素底部放置，宽度撑满选择区域
        # - fit_above: 紧贴参考元素顶部放置，宽度撑满选择区域
        # - align_top: 顶部对齐参考元素，宽度撑满选择区域
        # - align_bottom: 底部对齐参考元素，宽度撑满选择区域
        # - inside: 放置在参考元素内部

        if relative_position == "above":
            # 在参考元素上方：新中心 y = 参考元素顶部 y - 新元素高度/2 - offset_y
            new_cx = ref_cx + offset_x
            new_cy = reference_bounds["y"] - scaled_height / 2 - offset_y
        elif relative_position == "below":
            # 在参考元素下方：新中心 y = 参考元素底部 y + 新元素高度/2 - offset_y
            # 宽度默认使用参考元素宽度（与参考元素保持相近比例）
            new_cx = ref_cx + offset_x
            new_cy = reference_bounds["y"] + reference_bounds["height"] + scaled_height / 2 - offset_y
        elif relative_position == "left_of":
            # 在参考元素左侧：新中心 x = 参考元素左边 x - 新元素宽度/2 - offset_x
            new_cx = reference_bounds["x"] - scaled_width / 2 - offset_x
            new_cy = ref_cy + offset_y
        elif relative_position == "right_of":
            # 在参考元素右侧：新中心 x = 参考元素右边 x + 新元素宽度/2 - offset_x
            new_cx = reference_bounds["x"] + reference_bounds["width"] + scaled_width / 2 - offset_x
            new_cy = ref_cy + offset_y
        elif relative_position == "centered_on":
            # 中心对齐参考元素
            new_cx = ref_cx + offset_x
            new_cy = ref_cy + offset_y
        elif relative_position == "fit_below":
            # 紧贴参考元素底部放置在选择区域内，宽度撑满选择区域
            # 使用选择区域的高度进行缩放，而不是参考元素的高度
            fit_scaled_height = selection_bounds["height"] * scale
            # 计算可用高度
            available_height = (selection_bounds["y"] + selection_bounds["height"]) - (reference_bounds["y"] + reference_bounds["height"])
            # 使用可用高度或原高度的较小值，同时限制最大宽度
            fit_height = min(fit_scaled_height, available_height) if available_height > 0 else fit_scaled_height
            fit_width = selection_bounds["width"]
            # 居中放置
            new_cx = selection_bounds["x"] + fit_width / 2 + offset_x
            new_cy = reference_bounds["y"] + reference_bounds["height"] + fit_height / 2 + offset_y
            scaled_width = fit_width
            scaled_height = fit_height
        elif relative_position == "fit_above":
            # 紧贴参考元素顶部放置在选择区域内，宽度撑满选择区域
            # 使用选择区域的高度进行缩放
            fit_scaled_height = selection_bounds["height"] * scale
            available_height = reference_bounds["y"] - selection_bounds["y"]
            fit_height = min(fit_scaled_height, available_height) if available_height > 0 else fit_scaled_height
            fit_width = selection_bounds["width"]
            new_cx = selection_bounds["x"] + fit_width / 2 + offset_x
            new_cy = reference_bounds["y"] - fit_height / 2 + offset_y
            scaled_width = fit_width
            scaled_height = fit_height
        elif relative_position == "align_top":
            # 顶部对齐参考元素，宽度撑满选择区域
            fit_scaled_height = selection_bounds["height"] * scale
            fit_width = selection_bounds["width"]
            new_cx = selection_bounds["x"] + fit_width / 2 + offset_x
            new_cy = reference_bounds["y"] + fit_scaled_height / 2 + offset_y
            scaled_width = fit_width
            scaled_height = fit_scaled_height
        elif relative_position == "align_bottom":
            # 底部对齐参考元素，宽度撑满选择区域
            fit_scaled_height = selection_bounds["height"] * scale
            fit_width = selection_bounds["width"]
            new_cx = selection_bounds["x"] + fit_width / 2 + offset_x
            new_cy = reference_bounds["y"] + reference_bounds["height"] - fit_scaled_height / 2 + offset_y
            scaled_width = fit_width
            scaled_height = fit_scaled_height
        elif relative_position == "inside":
            # 放置在参考元素内部
            inside_x = reference_bounds["x"] + reference_bounds["width"] * (0.5 + offset_x)
            inside_y = reference_bounds["y"] + reference_bounds["height"] * (0.5 + offset_y)
            new_cx = inside_x
            new_cy = inside_y
        else:
            # 未知位置类型，使用参考元素中心 + offset
            new_cx = ref_cx + offset_x
            new_cy = ref_cy + offset_y

        # 计算新的 bounds（左上角坐标 + 缩放后的尺寸）
        new_x = new_cx - scaled_width / 2
        new_y = new_cy - scaled_height / 2

        result_bounds = {
            "x": new_x,
            "y": new_y,
            "width": scaled_width,
            "height": scaled_height
        }
        logger.info(f"[DEBUG _calculate_relative_position] returning: {result_bounds}")
        return result_bounds

    async def execute_streaming(self, operation: str,
                                params: Optional[Dict[str, Any]] = None) -> CanvasToolResult:
        """流式执行绘画 - 边绘制边发送进度"""
        from ..canvas.canvas_core import CanvasElement, ElementMetadata, ElementStyles, ElementType

        # 【调试日志1】params 获取颜色参数
        params = params or {}
        # 【修改】使用锁保护状态修改
        async with self._drawing_session_lock:
            raw_drawing_session_id = params.get("drawing_session_id") if params else None

            # 如果用户提供了 drawing_session_id，使用用户提供的
            if raw_drawing_session_id:
                self._current_drawing_session_id = raw_drawing_session_id
                self._drawing_session_count += 1
            # 如果 count == 0，自动生成新的 drawing_session_id
            elif self._drawing_session_count == 0:
                self._current_drawing_session_id = str(uuid.uuid4())[:8]  # 生成短ID便于识别
                self._drawing_session_count = 1
            else:
                # count > 0，复用当前的 drawing_session_id
                self._drawing_session_count += 1
        raw_stroke_color = params.get("color", "#000000")
        raw_stroke_width = params.get("stroke_width", 2)
        raw_fill_color = params.get("fill_color")

        selection_bounds = self._get_current_selection_bounds()
        if not selection_bounds:
            return CanvasToolResult(success=False,
                                  error="请先使用框选工具选择区域")

        stroke_color = params.get("color", "#000000")
        stroke_width = params.get("stroke_width", 2)
        fill_color = raw_fill_color or raw_stroke_color

        # 颜色转换
        stroke_color = self._ensure_hex_color(stroke_color)
        fill_color = self._ensure_hex_color(fill_color)

        self._ensure_progress_callback()

        # 【新增】处理相对定位 - 如果指定了 reference_element_id 和 relative_position
        reference_element_id = params.get("reference_element_id") if params else None
        relative_position = params.get("relative_position") if params else None
        use_relative_position = reference_element_id and relative_position

        draw_bounds = self._calculate_relative_position(
            selection_bounds, params
        )

        # 【Bounds检查】在创建元素之前验证边界
        is_valid, warning_msg = self._validate_bounds(draw_bounds, selection_bounds)
        if not is_valid:
            logger.warning(f"[CanvasDrawTool] Bounds validation failed: {warning_msg}")
            return CanvasToolResult(
                success=False,
                error=warning_msg,
                warning=warning_msg  # 返回警告信息给 Agent
            )

        # 创建元素（用于承载绘画结果）
        element_id = str(uuid.uuid4())
        element = CanvasElement(
            id=element_id,
            type=ElementType.SHAPE.value,
            position={"x": draw_bounds["x"], "y": draw_bounds["y"]},
            size={"width": draw_bounds.get("width", 100),
                  "height": draw_bounds.get("height", 100)},
            metadata=ElementMetadata(
                shape_type="path",
                points=[],
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                fill_color=fill_color
            ),
            styles=ElementStyles(
                x=draw_bounds["x"],
                y=draw_bounds["y"],
                width=draw_bounds.get("width", 100),
                height=draw_bounds.get("height", 100),
                stroke=stroke_color,
                stroke_width=stroke_width,
                fill=fill_color
            ),
            created_by="agent"
        )

        # 【新增】将 element_id 添加到 session 列表
        if self._current_drawing_session_id:
            if self._current_drawing_session_id not in self._session_element_ids:
                self._session_element_ids[self._current_drawing_session_id] = []
            self._session_element_ids[self._current_drawing_session_id].append(element_id)

        # 发送开始绘制事件
        if self.progress_callback:
            await self.progress_callback.send_start(element_id, operation)

        # 【SVG Path 支持】处理 path_data 参数
        path_data = params.get("path_data") if params else None
        svg_path = None  # 存储转换后的 SVG path

        # 生成绘画路径（根据操作类型）
        # 注意：如果使用了相对定位，scale 和 offset 已经体现在 draw_bounds 中了，
        # 所以不再传递给 _generate_path_points（避免双重应用）
        logger.info(f"[DEBUG execute_streaming] use_relative_position={use_relative_position}, draw_bounds={draw_bounds}")
        if use_relative_position:
            # 相对定位模式：bounds 已经调整过，path_points 生成时不再应用 scale/offset
            path_params = {}  # 清空 scale/offset，避免重复应用
        else:
            # 非相对定位模式：正常应用 scale/offset
            path_params = params

        # 【新增】如果提供了 path_data 且是 brush 操作，使用 SVG path
        if path_data and operation == "brush":
            # path_data 中的坐标是相对于选择区域的（0 到 width, 0 到 height）
            # 需要加上 draw_bounds 的偏移量
            offset_x = draw_bounds["x"]
            offset_y = draw_bounds["y"]
            svg_path, path_points = self._parse_svg_path(path_data, offset_x, offset_y)
            logger.info(f"[DEBUG execute_streaming] Using SVG path: {svg_path}")

            # 【新增】验证 SVG path 实际坐标是否超出选择区域
            # 选择区域的边界（绝对坐标）
            sel_x_start = selection_bounds["x"]
            sel_y_start = selection_bounds["y"]
            sel_x_end = sel_x_start + selection_bounds["width"]
            sel_y_end = sel_y_start + selection_bounds["height"]

            # 检查 path_points 是否超出选择区域
            if path_points:
                xs = [p[0] for p in path_points]
                ys = [p[1] for p in path_points]
                path_min_x, path_max_x = min(xs), max(xs)
                path_min_y, path_max_y = min(ys), max(ys)

                # 计算超出部分
                exceeds_parts = []
                if path_min_x < sel_x_start:
                    exceeds_parts.append(f"左边超出 {sel_x_start - path_min_x:.1f}px")
                if path_min_y < sel_y_start:
                    exceeds_parts.append(f"上边超出 {sel_y_start - path_min_y:.1f}px")
                if path_max_x > sel_x_end:
                    exceeds_parts.append(f"右边超出 {path_max_x - sel_x_end:.1f}px")
                if path_max_y > sel_y_end:
                    exceeds_parts.append(f"下边超出 {path_max_y - sel_y_end:.1f}px")

                if exceeds_parts:
                    warning_msg = (
                        f"【SVG Path 边界检查失败】路径坐标超出选择区域！\n"
                        f"路径边界: x=[{path_min_x:.1f}, {path_max_x:.1f}], y=[{path_min_y:.1f}, {path_max_y:.1f}]\n"
                        f"选择区域: x=[{sel_x_start:.1f}, {sel_x_end:.1f}], y=[{sel_y_start:.1f}, {sel_y_end:.1f}]\n"
                        f"超出部分: {', '.join(exceeds_parts)}\n"
                        f"\n"
                        f"【path_data 坐标规则】\n"
                        f"路径坐标应为画布绝对坐标。\n"
                        f"请调整 path_data 中的坐标，确保所有点都在选择区域内。"
                    )
                    logger.warning(f"[CanvasDrawTool] SVG path exceeds bounds: {exceeds_parts}")
                    return CanvasToolResult(
                        success=False,
                        error=warning_msg,
                        warning=warning_msg
                    )
        else:
            # 使用原有的点数组生成方式
            path_points = self._generate_path_points(operation, draw_bounds, path_params)

        # 计算路径的实际边界框
        if path_points:
            xs = [p[0] for p in path_points]
            ys = [p[1] for p in path_points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            actual_element_x = min_x
            actual_element_y = min_y
            actual_element_w = max_x - min_x
            actual_element_h = max_y - min_y
            logger.info(f"[DEBUG execute_streaming] path_points range: x=[{min_x}, {max_x}], y=[{min_y}, {max_y}]")
            logger.info(f"[DEBUG execute_streaming] actual_element_w={actual_element_w}, actual_element_h={actual_element_h}")
        else:
            actual_element_x = draw_bounds["x"]
            actual_element_y = draw_bounds["y"]
            actual_element_w = draw_bounds.get("width", 100)
            actual_element_h = draw_bounds.get("height", 100)

        # 更新元素的实际位置和尺寸
        # 使用绝对坐标存储（路径边界左上角）
        element.position = {"x": min_x, "y": min_y}
        element.size = {"width": actual_element_w, "height": actual_element_h}
        element.styles.x = actual_element_x
        element.styles.y = actual_element_y
        element.styles.width = actual_element_w
        element.styles.height = actual_element_h

        # 逐步发送绘画进度（使用相对坐标）
        current_points = []
        for i, point in enumerate(path_points):
            # 检查是否已取消
            if self._is_cancelled():
                logger.info("[CanvasDrawTool] Drawing cancelled by user")
                return CanvasToolResult(
                    success=False,
                    error="用户已取消操作"
                )

            # 直接存储绝对坐标（不再转换为相对坐标）
            current_points.append([point[0], point[1]])

            # 每隔一定数量的点发送一次进度
            if (i + 1) % 5 == 0 or i == len(path_points) - 1:
                if self.progress_callback:
                    await self.progress_callback.send_progress(
                        element_id,
                        current_points,
                        done=(i == len(path_points) - 1),
                        stroke_color=stroke_color,
                        stroke_width=stroke_width,
                        x=actual_element_x,
                        y=actual_element_y,
                        fill_color=fill_color
                    )

                # 短暂延迟以模拟绘制过程
                if i < len(path_points) - 1:
                    import asyncio
                    await asyncio.sleep(0.1)  # 100ms 延迟使绘制过程更明显

        # 更新元素的 points（使用相对于元素位置的坐标 {x, y} 格式）
        element.metadata.points = [{"x": p[0], "y": p[1]} for p in current_points]
        element.metadata.shape_type = "path"
        # 更新颜色参数（确保流式过程中可能修改的颜色被同步到 element）
        element.metadata.stroke_color = stroke_color
        element.metadata.fill_color = fill_color
        element.metadata.stroke_width = stroke_width
        # 更新 styles 中的颜色
        element.styles.stroke = stroke_color
        element.styles.fill = fill_color
        element.styles.stroke_width = stroke_width
        # 【新增】如果使用了 SVG path，更新到 metadata
        if svg_path:
            element.metadata.svg_path = svg_path

        element_dict = element.to_dict()

        # 【关键修复】先发送完成事件，再添加到后端
        # 确保 send_complete 发送的数据完全不依赖后端存储
        # 避免被 SYNC_STATE 覆盖导致前端收到错误数据
        if self.progress_callback:
            await self.progress_callback.send_complete(element_id, element.to_dict())

        # 添加元素到后端存储（用于持久化）
        success = await self.canvas.add_element(element)
        if not success:
            logger.warning(f"[CanvasDrawTool] Failed to add element to backend, continuing anyway")

        # 计算元素的实际 bounds（用于 Agent 智能定位）
        actual_bounds = {
            "x": element.position["x"],
            "y": element.position["y"],
            "width": element.size["width"],
            "height": element.size["height"]
        }

        # 验证 bounds 是否合理（防止错误计算导致的位置偏移过大）
        # 合理的 bounds：x/y 在 -10000 到 20000 之间
        is_valid_bounds = (
            -10000 < actual_bounds["x"] < 20000 and
            -10000 < actual_bounds["y"] < 20000 and
            0 < actual_bounds["width"] < 5000 and
            0 < actual_bounds["height"] < 5000
        )

        # 【修改】从 _tool_result_store 获取历史的 canvas_draw 结果来填充 _recent_elements
        # 这样即使跨工具调用，Agent 也能获取之前绘制元素的信息
        if self._tool_result_store and not self._recent_elements:
            self._recent_elements = self._load_recent_elements_from_store()

        # 记录最近绘制的元素（用于 Agent 智能定位）
        # 只有合理的 bounds 才会被记录
        if is_valid_bounds:
            element_info = {
                "element_id": element_id,
                "operation": operation,
                "bounds": actual_bounds,  # 使用实际 bounds，而非 selection_bounds
                "position": element.position,
                "size": element.size,
            }
            self._recent_elements.append(element_info)
            # 保持最多 MAX_RECENT_ELEMENTS 个元素
            if len(self._recent_elements) > self.MAX_RECENT_ELEMENTS:
                self._recent_elements.pop(0)
        else:
            logger.warning(f"[CanvasDrawTool] Skipping invalid bounds for recent_elements: {actual_bounds}")

        if success:
            # 【扩展】返回完整的元素数据，用于回撤和重新绘制
            element_data = element.to_dict()

            # 【新增】构建完整元素属性（element_full_attrs）
            element_full_attrs = self._build_element_full_attrs(element, actual_bounds)

            # 【新增】计算空间感知信息（spatial_hints）
            spatial_hints = self._build_spatial_hints(element, actual_bounds)

            # 【新增】自动分组和锁定：如果 session 中有多个元素，自动分组并锁定
            await self._auto_group_and_lock()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element_id,
                    "operation": operation,
                    "bounds": actual_bounds,  # 返回实际 bounds
                    "element_position": element.position,  # 额外提供位置信息
                    "element_size": element.size,  # 额外提供尺寸信息
                    "selection_bounds": selection_bounds,  # 保留选择区域供参考
                    "recent_elements": self._recent_elements.copy(),
                    # 【重构】完整元素数据，用于回撤和重新绘制
                    "element_data": element_data,
                    # 【新增】完整元素属性（增强版）
                    "element_full_attrs": element_full_attrs,
                    # 【新增】空间感知信息
                    "spatial_hints": spatial_hints,
                    "drawing_session_id": self._current_drawing_session_id,  # 新增
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="添加元素失败")

    def _build_element_full_attrs(self, element, bounds: Dict[str, float]) -> Dict[str, Any]:
        """构建完整元素属性（增强版）

        在 element.to_dict() 基础上，添加计算属性如中心点、右边/下边坐标等，
        让 Agent 能更方便地进行相对定位计算。

        Args:
            element: CanvasElement 实例
            bounds: 元素实际边界 {x, y, width, height}

        Returns:
            完整的元素属性字典
        """
        # 基础数据
        attrs = element.to_dict()

        # 添加计算属性
        x = bounds["x"]
        y = bounds["y"]
        width = bounds["width"]
        height = bounds["height"]

        attrs["computed"] = {
            # 中心点
            "center_x": x + width / 2,
            "center_y": y + height / 2,
            # 右边缘 x 坐标
            "right_edge_x": x + width,
            # 下边缘 y 坐标
            "bottom_edge_y": y + height,
            # 左边/右边/上边/下边 边缘位置（用于对齐检测）
            "left_edge": x,
            "right_edge": x + width,
            "top_edge": y,
            "bottom_edge": y + height,
        }

        # 添加样式便捷访问
        if element.styles:
            attrs["styles_summary"] = {
                "fill": element.styles.fill,
                "stroke": element.styles.stroke,
                "stroke_width": element.styles.stroke_width,
                "opacity": element.styles.opacity,
                "rotation": element.styles.rotation,
            }

        return attrs

    def _build_spatial_hints(self, element, bounds: Dict[str, float]) -> Dict[str, Any]:
        """构建空间感知信息

        分析当前元素与其他元素的空间关系，提供对齐和距离信息，
        帮助 Agent 更好地进行相对定位。

        Args:
            element: CanvasElement 实例
            bounds: 元素实际边界 {x, y, width, height}

        Returns:
            空间感知信息字典，包含 aligned_with 和 distance_to_nearest_edge
        """
        spatial_hints = {
            "aligned_with": [],       # 对齐关系列表
            "distance_to_nearest_edge": None,  # 到最近边缘的距离
        }

        if not self.canvas or not self.canvas._elements:
            return spatial_hints

        try:
            # 获取当前元素的几何信息
            current_left = bounds["x"]
            current_right = bounds["x"] + bounds["width"]
            current_top = bounds["y"]
            current_bottom = bounds["y"] + bounds["height"]

            # 获取 canvas 所有元素（排除自己）
            other_elements = []
            for elem_id, elem in self.canvas._elements.items():
                if elem_id == element.id:
                    continue
                if not elem.visible:
                    continue
                elem_bounds = elem.get_bounds()
                other_elements.append({
                    "id": elem_id,
                    "type": elem.type,
                    "bounds": elem_bounds,
                })

            if not other_elements:
                return spatial_hints

            # 用于找最近距离
            min_distance = float("inf")
            nearest_edge_info = None

            # 用于记录对齐关系
            alignment_tolerance = 5  # 5px 容差

            for other in other_elements:
                other_bounds = other["bounds"]
                other_left = other_bounds["x"]
                other_right = other_bounds["x"] + other_bounds["width"]
                other_top = other_bounds["y"]
                other_bottom = other_bounds["y"] + other_bounds["height"]
                other_id = other["id"]

                # 检测左边缘对齐
                if abs(current_left - other_left) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.left")
                # 检测右边缘对齐
                elif abs(current_right - other_right) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.right")
                # 检测左边缘对右边缘
                elif abs(current_left - other_right) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.right_edge")
                # 检测右边缘对左边缘
                elif abs(current_right - other_left) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.left_edge")

                # 检测上边缘对齐
                if abs(current_top - other_top) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.top")
                # 检测下边缘对齐
                elif abs(current_bottom - other_bottom) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.bottom")
                # 检测上边缘对下边缘
                elif abs(current_top - other_bottom) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.bottom_edge")
                # 检测下边缘对上边缘
                elif abs(current_bottom - other_top) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.top_edge")

                # 检测中心点对齐（水平）
                current_center_x = current_left + bounds["width"] / 2
                other_center_x = other_left + other_bounds["width"] / 2
                if abs(current_center_x - other_center_x) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.center_x")

                # 检测中心点对齐（垂直）
                current_center_y = current_top + bounds["height"] / 2
                other_center_y = other_top + other_bounds["height"] / 2
                if abs(current_center_y - other_center_y) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.center_y")

                # 计算到其他元素的最小距离
                # 水平距离（当前元素在左边时）
                if current_right < other_left:
                    horiz_dist = other_left - current_right
                elif current_left > other_right:
                    horiz_dist = current_left - other_right
                else:
                    horiz_dist = 0  # 水平重叠

                # 垂直距离（当前元素在上边时）
                if current_bottom < other_top:
                    vert_dist = other_top - current_bottom
                elif current_top > other_bottom:
                    vert_dist = current_top - other_bottom
                else:
                    vert_dist = 0  # 垂直重叠

                # 总距离（水平+垂直，曼哈顿距离）
                distance = horiz_dist + vert_dist

                if distance > 0 and distance < min_distance:
                    min_distance = distance
                    nearest_edge_info = {
                        "distance": min_distance,
                        "direction": self._get_distance_direction(
                            current_left, current_right, current_top, current_bottom,
                            other_left, other_right, other_top, other_bottom
                        )
                    }

            # 设置最近距离
            if nearest_edge_info:
                spatial_hints["distance_to_nearest_edge"] = nearest_edge_info["distance"]
                spatial_hints["nearest_edge_direction"] = nearest_edge_info["direction"]

        except Exception as e:
            logger.warning(f"[CanvasDrawTool] Failed to build spatial hints: {e}")

        return spatial_hints

    def _get_distance_direction(self,
                                cur_left: float, cur_right: float,
                                cur_top: float, cur_bottom: float,
                                oth_left: float, oth_right: float,
                                oth_top: float, oth_bottom: float) -> str:
        """计算当前元素到目标元素的距离方向

        Returns:
            方向字符串，如 "right", "below", "right-below" 等
        """
        directions = []

        if cur_right <= oth_left:
            directions.append("right")
        elif cur_left >= oth_right:
            directions.append("left")

        if cur_bottom <= oth_top:
            directions.append("below")
        elif cur_top >= oth_bottom:
            directions.append("above")

        return "-".join(directions) if directions else "overlapping"

    async def _auto_group_and_lock(self):
        """自动分组并锁定（Agent 绘制完成时调用）

        如果当前 session 中有多个元素，自动将它们分组并锁定。
        分组后，组合及其所有子元素都会被锁定。
        """
        session_id = self._current_drawing_session_id
        session_count = self._drawing_session_count

        logger.info(f"[CanvasDrawTool] Auto grouping: session={session_id}, count={session_count}")

        # 如果有多个元素且有 session_id，自动分组
        if session_id and session_count >= 2:
            try:
                # 从 _session_element_ids 获取该会话的所有元素 ID
                element_ids = self._session_element_ids.get(session_id, [])

                if len(element_ids) >= 2:
                    logger.info(f"[CanvasDrawTool] Auto grouping {len(element_ids)} elements for session: {session_id}")

                    # 调用 canvas 的分组操作
                    if self.canvas:
                        from ..canvas.canvas_core import CanvasOperation, OperationType
                        op = CanvasOperation(
                            id=self.canvas._generate_id(),
                            type="group",
                            target_ids=element_ids,
                            after_state={},
                            creator="agent",
                        )
                        # 执行分组操作（分组操作本身会设置 locked=True）
                        await self.canvas.execute_operation(op)
                        logger.info(f"[CanvasDrawTool] Auto grouping completed for session: {session_id}")

                        # 重置计数器，开始新的绘画会话
                        self._drawing_session_count = 0
                        self._current_drawing_session_id = None
                        # 清除该 session 的元素列表
                        if session_id in self._session_element_ids:
                            del self._session_element_ids[session_id]
                        logger.info("[CanvasDrawTool] Drawing session counter reset after auto grouping")
            except Exception as e:
                logger.error(f"[CanvasDrawTool] Error during auto grouping: {e}")

    def reset_drawing_session(self):
        """重置绘图会话（用户点击'绘制完成'按钮时调用）

        会将同一次绘画会话的所有元素自动分组
        """
        # 保存当前 session_id 以便获取元素后分组
        session_id = self._current_drawing_session_id
        session_count = self._drawing_session_count

        logger.info(f"[CanvasDrawTool] Resetting drawing session: {session_id}, elements count: {session_count}")

        # 如果有多个元素且有 session_id，自动分组
        if session_id and session_count >= 2:
            try:
                # 从 _session_element_ids 获取该会话的所有元素 ID
                element_ids = self._session_element_ids.get(session_id, [])

                if len(element_ids) >= 2:
                    logger.info(f"[CanvasDrawTool] Grouping {len(element_ids)} elements for session: {session_id}")

                    # 调用 canvas 的分组操作
                    if self.canvas:
                        from ..canvas.canvas_core import CanvasOperation, OperationType
                        op = CanvasOperation(
                            id=self.canvas._generate_id(),
                            type="group",
                            target_ids=element_ids,
                            after_state={},
                            creator="agent",
                        )
                        # 同步执行分组（不使用 await）
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # 如果已经在运行，创建一个任务
                                asyncio.create_task(self.canvas.execute_operation(op))
                            else:
                                loop.run_until_complete(self.canvas.execute_operation(op))
                            logger.info(f"[CanvasDrawTool] Grouping completed for session: {session_id}")
                        except Exception as group_err:
                            logger.error(f"[CanvasDrawTool] Failed to group elements: {group_err}")
            except Exception as e:
                logger.error(f"[CanvasDrawTool] Error during grouping: {e}")

        # 重置计数器
        self._drawing_session_count = 0
        self._current_drawing_session_id = None
        # 清除该 session 的元素列表
        if session_id and session_id in self._session_element_ids:
            del self._session_element_ids[session_id]
        logger.info("[CanvasDrawTool] Drawing session reset")

    def _load_recent_elements_from_store(self) -> List[Dict[str, Any]]:
        """
        从 _tool_result_store 加载历史的 canvas_draw 结果

        用于在跨工具调用时，Agent 仍能获取之前绘制元素的信息。
        """
        if not self._tool_result_store:
            return []

        try:
            # 获取最近 MAX_RECENT_ELEMENTS 个 canvas_draw 结果
            history = self._tool_result_store.get_history(tool_name="canvas_draw", limit=self.MAX_RECENT_ELEMENTS)

            recent_elements = []
            for record in reversed(history):  # 反转，最新的在前
                result_data = record.result_data
                if result_data and isinstance(result_data, dict):
                    bounds = result_data.get("bounds")
                    if bounds:
                        element_info = {
                            "element_id": result_data.get("element_id"),
                            "operation": result_data.get("operation", "brush"),
                            "bounds": bounds,
                            "position": result_data.get("element_position"),
                            "size": result_data.get("element_size"),
                        }
                        # 【新增】如果 result_data 中有完整元素属性和空间感知，也一并加入
                        if result_data.get("element_full_attrs"):
                            element_info["element_full_attrs"] = result_data.get("element_full_attrs")
                        if result_data.get("spatial_hints"):
                            element_info["spatial_hints"] = result_data.get("spatial_hints")
                        recent_elements.append(element_info)

            return recent_elements
        except Exception as e:
            logger.warning(f"[CanvasDrawTool] Failed to load recent elements from store: {e}")
            return []

    def _generate_path_points(self, operation: str,
                             bounds: Dict[str, float],
                             params: Dict[str, Any]) -> List[List[float]]:
        """
        根据操作类型生成路径点。

        支持通过 params 控制图形的位置和大小：
        - scale: 图形占区域的比例 (0.0-1.0)，默认 1.0 表示占满整个区域
        - offset_x: 图形中心在区域的横向偏移比例 (-0.5 到 0.5)，默认 0
        - offset_y: 图形中心在区域的纵向偏移比例 (-0.5 到 0.5)，默认 0
        """
        x, y = bounds["x"], bounds["y"]
        w, h = bounds.get("width", 100), bounds.get("height", 100)

        # 获取缩放和偏移参数
        scale = params.get("scale", 1.0) if params else 1.0
        offset_x = params.get("offset_x", 0.0) if params else 0.0
        offset_y = params.get("offset_y", 0.0) if params else 0.0

        # 计算偏移后的图形中心点
        offset_pixel_x = w * offset_x
        offset_pixel_y = h * offset_y

        # 计算缩放后的尺寸
        scaled_w = w * scale
        scaled_h = h * scale

        if operation == "circle":
            # 生成圆形路径（使用较小的缩放尺寸保持宽高比）
            radius = min(scaled_w, scaled_h) / 2
            cx = x + scaled_w/2 + offset_pixel_x
            cy = y + scaled_h/2 + offset_pixel_y
            points = []
            for i in range(37):  # 0 到 360 度
                angle = i * 10 * math.pi / 180
                px = cx + radius * math.cos(angle)
                py = cy + radius * math.sin(angle)
                points.append([px, py])
            return points

        elif operation == "ellipse":
            # 生成椭圆路径
            cx = x + scaled_w/2 + offset_pixel_x
            cy = y + scaled_h/2 + offset_pixel_y
            rx = scaled_w / 2
            ry = scaled_h / 2
            points = []
            for i in range(37):  # 0 到 360 度
                angle = i * 10 * math.pi / 180
                px = cx + rx * math.cos(angle)
                py = cy + ry * math.sin(angle)
                points.append([px, py])
            return points

        elif operation == "rect":
            # 生成矩形路径
            rect_w = scaled_w
            rect_h = scaled_h
            # 矩形的起始点（左上角）
            rect_x = x + offset_pixel_x
            rect_y = y + offset_pixel_y
            return [
                [rect_x, rect_y],
                [rect_x + rect_w, rect_y],
                [rect_x + rect_w, rect_y + rect_h],
                [rect_x, rect_y + rect_h],
                [rect_x, rect_y]
            ]

        elif operation == "line":
            # 生成直线（居中）
            line_y = y + scaled_h/2 + offset_pixel_y
            line_x_start = x + offset_pixel_x
            line_x_end = x + scaled_w + offset_pixel_x
            return [[line_x_start, line_y], [line_x_end, line_y]]

        elif operation == "polygon":
            # 生成多边形（爱心形状示例）
            heart_points = []
            for i in range(37):
                t = i * 10 * math.pi / 180
                hx = 16 * math.sin(t) ** 3
                hy = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
                # 缩放到目标区域
                scale_factor = min(scaled_w, scaled_h) / 32
                px = x + scaled_w/2 + offset_pixel_x + hx * scale_factor
                py = y + scaled_h/2 + offset_pixel_y + hy * scale_factor
                heart_points.append([px, py])
            return heart_points

        elif operation == "brush":
            # 生成自由曲线/画笔效果（波浪形）
            # 在区域内生成一条自然流畅的波浪线
            brush_points = []
            num_waves = 3  # 波浪数量
            amplitude = scaled_h * 0.3  # 振幅

            for i in range(num_waves * 10 + 1):  # 每波浪10个点
                t = i / 10.0
                px = x + (t / num_waves) * scaled_w + offset_pixel_x
                # 正弦波
                py = y + scaled_h/2 + offset_pixel_y + amplitude * math.sin(t * 2 * math.pi)
                brush_points.append([px, py])

            return brush_points

        elif operation == "star":
            # 生成五角星
            return self._generate_star_points(x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)

        elif operation == "triangle":
            # 生成三角形
            return self._generate_triangle_points(x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)

        elif operation == "arrow":
            # 生成箭头
            return self._generate_arrow_points(x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)

        elif operation == "diamond":
            # 生成菱形
            return self._generate_diamond_points(x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)

        elif operation == "hexagon":
            # 生成六边形
            return self._generate_hexagon_points(x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)

        elif operation == "pentagon":
            # 生成五边形
            return self._generate_polygon_points(x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y, 5)

        elif operation == "cross":
            # 生成十字形
            return self._generate_cross_points(x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)

        else:
            return [[x, y], [x + w, y + h]]

    def _generate_star_points(self, x: float, y: float, w: float, h: float,
                              offset_x: float, offset_y: float) -> List[List[float]]:
        """生成五角星路径点"""
        center_x = x + w / 2 + offset_x
        center_y = y + h / 2 + offset_y
        outer_radius = min(w, h) / 2
        inner_radius = outer_radius * 0.382  # 五角星内半径比例

        points = []
        for i in range(10):
            angle = (i * 36 - 90) * math.pi / 180  # 从顶部开始
            radius = outer_radius if i % 2 == 0 else inner_radius
            px = center_x + radius * math.cos(angle)
            py = center_y + radius * math.sin(angle)
            points.append([px, py])
        points.append(points[0])  # 闭合
        return points

    def _generate_triangle_points(self, x: float, y: float, w: float, h: float,
                                   offset_x: float, offset_y: float) -> List[List[float]]:
        """生成三角形路径点"""
        return [
            [x + w / 2 + offset_x, y + offset_y],  # 顶部
            [x + w + offset_x, y + h + offset_y],   # 右下
            [x + offset_x, y + h + offset_y],       # 左下
            [x + w / 2 + offset_x, y + offset_y]   # 闭合
        ]

    def _generate_arrow_points(self, x: float, y: float, w: float, h: float,
                              offset_x: float, offset_y: float) -> List[List[float]]:
        """生成箭头路径点"""
        arrow_head_ratio = 0.3  # 箭头占整体的比例
        shaft_ratio = 0.4       # 箭杆占整体的比例

        # 计算各部分尺寸
        arrow_head_w = w * arrow_head_ratio
        shaft_h = h * shaft_ratio
        shaft_w = w * 0.15

        # 中心位置
        center_x = x + w / 2 + offset_x
        center_y = y + h / 2 + offset_y

        # 箭头底部起点
        arrow_bottom = y + h - (h - shaft_h) / 2 + offset_y
        arrow_top = y + (h - shaft_h) / 2 + offset_y

        points = [
            [center_x, y + offset_y],                           # 箭头尖端
            [center_x + arrow_head_w / 2, y + h * arrow_head_ratio + offset_y],  # 右上
            [center_x + shaft_w / 2, arrow_top],                 # 右上连接
            [center_x + shaft_w / 2, arrow_bottom],              # 右下杆
            [center_x + arrow_head_w / 2, arrow_bottom],         # 右下连接
            [center_x + arrow_head_w / 2, y + h + offset_y],    # 右下箭头
            [center_x - arrow_head_w / 2, y + h + offset_y],    # 左下箭头
            [center_x - arrow_head_w / 2, arrow_bottom],         # 左下连接
            [center_x - shaft_w / 2, arrow_bottom],              # 左下杆
            [center_x - shaft_w / 2, arrow_top],                 # 左上杆
            [center_x - arrow_head_w / 2, arrow_top],             # 左上连接
            [center_x - arrow_head_w / 2, y + h * arrow_head_ratio + offset_y],  # 左上
            [center_x, y + offset_y]                             # 回到尖端
        ]
        return points

    def _generate_diamond_points(self, x: float, y: float, w: float, h: float,
                                 offset_x: float, offset_y: float) -> List[List[float]]:
        """生成菱形路径点"""
        center_x = x + w / 2 + offset_x
        center_y = y + h / 2 + offset_y
        return [
            [center_x, y + offset_y],           # 上
            [x + w + offset_x, center_y],       # 右
            [center_x, y + h + offset_y],      # 下
            [x + offset_x, center_y],           # 左
            [center_x, y + offset_y]            # 闭合
        ]

    def _generate_hexagon_points(self, x: float, y: float, w: float, h: float,
                                offset_x: float, offset_y: float) -> List[List[float]]:
        """生成六边形路径点"""
        center_x = x + w / 2 + offset_x
        center_y = y + h / 2 + offset_y
        radius = min(w, h) / 2

        points = []
        for i in range(6):
            angle = (i * 60 - 90) * math.pi / 180  # 从顶部开始
            px = center_x + radius * math.cos(angle)
            py = center_y + radius * math.sin(angle)
            points.append([px, py])
        points.append(points[0])  # 闭合
        return points

    def _generate_polygon_points(self, x: float, y: float, w: float, h: float,
                                offset_x: float, offset_y: float, sides: int) -> List[List[float]]:
        """生成正多边形路径点"""
        center_x = x + w / 2 + offset_x
        center_y = y + h / 2 + offset_y
        radius = min(w, h) / 2

        points = []
        for i in range(sides):
            angle = (i * 360 / sides - 90) * math.pi / 180  # 从顶部开始
            px = center_x + radius * math.cos(angle)
            py = center_y + radius * math.sin(angle)
            points.append([px, py])
        points.append(points[0])  # 闭合
        return points

    def _generate_cross_points(self, x: float, y: float, w: float, h: float,
                              offset_x: float, offset_y: float) -> List[List[float]]:
        """生成十字形路径点"""
        arm_ratio = 0.35  # 臂宽占整体的比例
        arm_w = w * arm_ratio
        arm_h = h * arm_ratio

        center_x = x + w / 2 + offset_x
        center_y = y + h / 2 + offset_y

        # 十字形由中心矩形和四个臂组成
        points = [
            [center_x - arm_w / 2, center_y - arm_h / 2],  # 左上内
            [center_x + arm_w / 2, center_y - arm_h / 2],    # 右上内
            [center_x + arm_w / 2, y + offset_y],           # 上臂
            [center_x + w / 2, y + offset_y],               # 右上尖
            [center_x + w / 2, center_y - arm_h / 2],       # 右臂上
            [center_x + arm_w / 2 + (w - arm_w) / 2, center_y - arm_h / 2],  # 右上内
            [center_x + arm_w / 2 + (w - arm_w) / 2, center_y + arm_h / 2],  # 右下内
            [center_x + w / 2, center_y + arm_h / 2],       # 右臂下
            [center_x + w / 2, y + h + offset_y],          # 右下尖
            [center_x + arm_w / 2, y + h + offset_y],      # 下臂
            [center_x + arm_w / 2, center_y + arm_h / 2],   # 右下内
            [center_x - arm_w / 2, center_y + arm_h / 2],   # 左下内
            [center_x - arm_w / 2, y + h + offset_y],      # 下臂
            [center_x - w / 2, y + h + offset_y],           # 左下尖
            [center_x - w / 2, center_y + arm_h / 2],       # 左臂下
            [center_x - arm_w / 2 - (w - arm_w) / 2, center_y + arm_h / 2],  # 左下内
            [center_x - arm_w / 2 - (w - arm_w) / 2, center_y - arm_h / 2],  # 左上内
            [center_x - w / 2, center_y - arm_h / 2],       # 左臂上
            [center_x - w / 2, y + offset_y],               # 左上尖
            [center_x - arm_w / 2, y + offset_y],           # 上臂
            [center_x - arm_w / 2, center_y - arm_h / 2],   # 左上内
        ]
        return points

    def _parse_svg_path(self, path_data: str, offset_x: float = 0, offset_y: float = 0) -> tuple[str, list]:
        """
        解析 SVG path 命令字符串，将其转换为绝对坐标，并计算边界框。

        支持多路径格式：多个子路径用空格、换行或分号分隔。
        每个子路径可以独立绘制，组合成一个完整的 SVG path。

        例如：
        - "M 0 0 L 50 50 M 100 100 L 150 150" （两个独立的线段）
        - "M 10 10 Q 30 0 50 10 T 90 10 M 50 20 A 5 5 0 1 1 60 20 A 5 5 0 1 1 50 20" （笑脸）

        Args:
            path_data: SVG path 命令字符串，支持单路径或多路径
            offset_x: X 轴偏移量
            offset_y: Y 轴偏移量

        Returns:
            tuple: (转换后的 SVG path 字符串, 点数组 [[x, y], ...])
        """
        import re

        # 【修改】通过找所有 M 命令的位置来分割子路径，而不是简单的空格分割
        # 这样可以正确处理 A 等多参数命令

        # 找到所有 M 命令的位置
        path_data_upper = path_data.upper()
        m_positions = [m.start() for m in re.finditer(r'M', path_data_upper)]

        if not m_positions:
            # 没有 M 命令，无法解析
            return path_data, []

        # 分割成多个子路径
        sub_paths = []
        for i, pos in enumerate(m_positions):
            if i < len(m_positions) - 1:
                # 子路径从当前 M 到下一个 M 之前
                sub_path = path_data[pos:m_positions[i+1]].strip()
            else:
                # 最后一个子路径
                sub_path = path_data[pos:].strip()
            if sub_path:
                sub_paths.append(sub_path)

        if not sub_paths:
            return path_data, []

        # 如果只有一个路径，直接解析
        if len(sub_paths) == 1:
            return self._parse_single_svg_path(sub_paths[0], offset_x, offset_y)

        # 多路径：分别解析每个子路径，然后合并
        all_points = []
        result_path_parts = []

        for sub_path in sub_paths:
            # 跳过空路径
            if not sub_path.strip():
                continue

            # 解析单个子路径
            parsed_path, sub_points = self._parse_single_svg_path(sub_path, offset_x, offset_y)
            if parsed_path:
                result_path_parts.append(parsed_path)
                all_points.extend(sub_points)

        # 合并所有子路径为一个完整的 SVG path
        # 注意：SVG path 中多个 M 命令会创建多个子路径
        combined_path = " ".join(result_path_parts)

        return combined_path, all_points

    def _parse_single_svg_path(self, path_data: str, offset_x: float = 0, offset_y: float = 0) -> tuple[str, list]:
        """
        解析单个 SVG path 命令字符串。

        Args:
            path_data: SVG path 命令字符串
            offset_x: X 轴偏移量
            offset_y: Y 轴偏移量

        Returns:
            tuple: (转换后的 SVG path 字符串, 点数组 [[x, y], ...])
        """
        import re

        # 解析命令和参数
        # 支持的命令: M, L, Q, C, A, Z, T (大写表示绝对坐标)
        command_pattern = r'([MLQCAZT])\s*([-\d.,\s]*)'
        matches = re.findall(command_pattern, path_data.upper())

        if not matches:
            return path_data, []

        points = []
        current_x, current_y = 0, 0
        result_path_parts = []

        # 二次贝塞尔曲线的控制点（用于 T 命令）
        last_qx, last_qy = None, None

        for command, args_str in matches:
            # 先将逗号替换为空格，再分割处理数值
            args_str_clean = args_str.replace(',', ' ')
            args = [float(x) for x in args_str_clean.strip().split() if x]

            if command == 'M':  # MoveTo
                x = args[0] + offset_x
                y = args[1] + offset_y
                result_path_parts.append(f"M {x} {y}")
                points.append([x, y])
                current_x, current_y = x, y

            elif command == 'L':  # LineTo
                x = args[0] + offset_x
                y = args[1] + offset_y
                result_path_parts.append(f"L {x} {y}")
                points.append([x, y])
                current_x, current_y = x, y

            elif command == 'Q':  # 二次贝塞尔曲线
                if len(args) >= 4:
                    cx = args[0] + offset_x
                    cy = args[1] + offset_y
                    x = args[2] + offset_x
                    y = args[3] + offset_y
                    result_path_parts.append(f"Q {cx} {cy} {x} {y}")
                    points.append([cx, cy])  # 控制点
                    points.append([x, y])    # 终点
                    last_qx, last_qy = cx, cy
                    current_x, current_y = x, y

            elif command == 'C':  # 三次贝塞尔曲线
                if len(args) >= 6:
                    cx1 = args[0] + offset_x
                    cy1 = args[1] + offset_y
                    cx2 = args[2] + offset_x
                    cy2 = args[3] + offset_y
                    x = args[4] + offset_x
                    y = args[5] + offset_y
                    result_path_parts.append(f"C {cx1} {cy1} {cx2} {cy2} {x} {y}")
                    points.append([cx1, cy1])
                    points.append([cx2, cy2])
                    points.append([x, y])
                    current_x, current_y = x, y

            elif command == 'A':  # 圆弧
                if len(args) >= 7:
                    rx = args[0]
                    ry = args[1]
                    x = args[5] + offset_x
                    y = args[6] + offset_y
                    result_path_parts.append(f"A {rx} {ry} {args[2]} {args[3]} {args[4]} {x} {y}")
                    points.append([x, y])
                    current_x, current_y = x, y

            elif command == 'Z':  # 闭合路径
                result_path_parts.append("Z")

        # 对于 T 命令（平滑二次贝塞尔），需要特殊处理
        # 简化处理：如果原 path 有 T，重新构建
        if 'T' in path_data.upper():
            # 重新解析，保留 T 命令的原始结构
            result_path_parts = []
            tokens = re.findall(r'([MLQCAZT])\s*([-\d.,\s]*)', path_data.upper())
            current_x, current_y = 0, 0
            last_qx, last_qy = None, None

            for command, args_str in tokens:
                args = [float(x) for x in args_str.strip().split() if x]

                if command == 'M':
                    x = args[0] + offset_x
                    y = args[1] + offset_y
                    result_path_parts.append(f"M {x} {y}")
                    current_x, current_y = x, y

                elif command == 'L':
                    x = args[0] + offset_x
                    y = args[1] + offset_y
                    result_path_parts.append(f"L {x} {y}")
                    current_x, current_y = x, y

                elif command == 'Q':
                    if len(args) >= 4:
                        cx = args[0] + offset_x
                        cy = args[1] + offset_y
                        x = args[2] + offset_x
                        y = args[3] + offset_y
                        result_path_parts.append(f"Q {cx} {cy} {x} {y}")
                        last_qx, last_qy = cx, cy
                        current_x, current_y = x, y

                elif command == 'T':
                    # T 命令：控制点是上一个 Q 控制点关于当前点的对称点
                    if last_qx is not None:
                        rx = 2 * current_x - last_qx
                        ry = 2 * current_y - last_qy
                    else:
                        rx, ry = current_x, current_y
                    x = args[0] + offset_x
                    y = args[1] + offset_y
                    result_path_parts.append(f"Q {rx} {ry} {x} {y}")
                    last_qx, last_qy = rx, ry
                    current_x, current_y = x, y

                elif command == 'C':
                    if len(args) >= 6:
                        cx1 = args[0] + offset_x
                        cy1 = args[1] + offset_y
                        cx2 = args[2] + offset_x
                        cy2 = args[3] + offset_y
                        x = args[4] + offset_x
                        y = args[5] + offset_y
                        result_path_parts.append(f"C {cx1} {cy1} {cx2} {cy2} {x} {y}")
                        current_x, current_y = x, y

                elif command == 'A':
                    if len(args) >= 7:
                        x = args[5] + offset_x
                        y = args[6] + offset_y
                        result_path_parts.append(f"A {args[0]} {args[1]} {args[2]} {args[3]} {args[4]} {x} {y}")
                        current_x, current_y = x, y

                elif command == 'Z':
                    result_path_parts.append("Z")

        return " ".join(result_path_parts), points

    def _svg_path_to_points(self, path_data: str, num_samples: int = 50) -> list:
        """
        将 SVG path 转换为采样点数组（用于流式发送和边界计算）。

        Args:
            path_data: SVG path 命令字符串
            num_samples: 每个曲线命令的采样点数

        Returns:
            点数组 [[x, y], ...]
        """
        import re

        points = []
        current_x, current_y = 0, 0

        # 解析命令
        command_pattern = r'([MLQCAZ])\s*([-\d.,\s]*)'
        matches = re.findall(command_pattern, path_data.upper())

        for command, args_str in matches:
            # 先将逗号替换为空格，再分割处理数值
            args_str_clean = args_str.replace(',', ' ')
            args = [float(x) for x in args_str_clean.strip().split() if x]

            if command == 'M':
                current_x = args[0]
                current_y = args[1]
                points.append([current_x, current_y])

            elif command == 'L':
                current_x = args[0]
                current_y = args[1]
                points.append([current_x, current_y])

            elif command == 'Q':
                if len(args) >= 4:
                    cx, cy = args[0], args[1]
                    ex, ey = args[2], args[3]
                    for i in range(num_samples):
                        t = i / (num_samples - 1)
                        # 二次贝塞尔公式: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
                        x = (1-t)*(1-t)*current_x + 2*(1-t)*t*cx + t*t*ex
                        y = (1-t)*(1-t)*current_y + 2*(1-t)*t*cy + t*t*ey
                        points.append([x, y])
                    current_x, current_y = ex, ey

            elif command == 'C':
                if len(args) >= 6:
                    cx1, cy1 = args[0], args[1]
                    cx2, cy2 = args[2], args[3]
                    ex, ey = args[4], args[5]
                    for i in range(num_samples):
                        t = i / (num_samples - 1)
                        # 三次贝塞尔公式
                        x = (1-t)*(1-t)*(1-t)*current_x + 3*(1-t)*(1-t)*t*cx1 + 3*(1-t)*t*t*cx2 + t*t*t*ex
                        y = (1-t)*(1-t)*(1-t)*current_y + 3*(1-t)*(1-t)*t*cy1 + 3*(1-t)*t*t*cy2 + t*t*t*ey
                        points.append([x, y])
                    current_x, current_y = ex, ey

            elif command == 'A':
                # 简化处理：圆弧直接用终点
                if len(args) >= 7:
                    current_x = args[5]
                    current_y = args[6]
                    points.append([current_x, current_y])

            elif command == 'Z':
                pass  # 闭合路径不添加额外点

        return points

    def _ensure_hex_color(self, color: str) -> str:
        """将颜色名称转换为十六进制"""
        color_map = {
            "red": "#FF0000", "green": "#00FF00", "blue": "#0000FF",
            "yellow": "#FFFF00", "orange": "#FFA500", "purple": "#800080",
            "pink": "#FFC0CB", "black": "#000000", "white": "#FFFFFF",
            "gray": "#808080", "grey": "#808080",
        }
        return color_map.get(color.lower(), color)


class GetCanvasToolResultTool(Tool):
    """查询画板工具历史结果工具

    用于查询画板Agent的工具调用历史结果。
    """

    def __init__(self, tool_result_store, canvas_id: str = None):
        self._store = tool_result_store
        self._canvas_id = canvas_id

    @property
    def name(self) -> str:
        return "get_canvas_tool_result"

    @property
    def description(self) -> str:
        return """查询画板工具的历史执行结果。

用于获取之前工具调用的结果，支持按工具名、元素ID、绘图会话ID、字段查询。

输入：
- tool_name: 工具名称（可选），如 draw, generate, edit 等
- index: 版本索引（默认0），0=最老版本，1=第二个版本，以此类推
- element_id: 元素ID（可选），查询与特定元素相关的工具结果
- drawing_session_id: 绘图会话ID（可选），查询与特定绘图会话相关的工具结果
- field: 字段名（可选），从结果中获取特定字段
- history: 是否返回历史列表（默认false）

返回：
- 如果 history=true，返回所有匹配的历史记录列表
- 如果指定 field，返回该字段的值
- 否则返回完整的工具结果"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "工具名称（可选），如 draw, generate, edit, understand, suggest 等"
                },
                "index": {
                    "type": "integer",
                    "description": "版本索引（默认0），0=最老版本，1=第二个版本，以此类推"
                },
                "element_id": {
                    "type": "string",
                    "description": "元素ID（可选），查询与特定元素相关的工具结果"
                },
                "drawing_session_id": {
                    "type": "string",
                    "description": "绘图会话ID（可选），查询与特定绘图会话相关的工具结果"
                },
                "field": {
                    "type": "string",
                    "description": "字段名（可选），从结果中获取特定字段值"
                },
                "history": {
                    "type": "boolean",
                    "description": "是否返回历史列表（默认false）"
                }
            },
            "required": []
        }

    async def execute(
        self,
        tool_name: Optional[str] = None,
        index: int = 0,
        element_id: Optional[str] = None,
        drawing_session_id: Optional[str] = None,  # 新增参数
        field: Optional[str] = None,
        history: bool = False,
    ) -> CanvasToolResult:
        try:
            # 按 drawing_session_id 查询
            if drawing_session_id:
                records = self._store.get_by_drawing_session(drawing_session_id)
                # 【新增】内存没有则查归档
                if not records and self._canvas_id:
                    archive_data = self._store.get_archive_by_drawing_session_id(self._canvas_id, drawing_session_id)
                    if archive_data:
                        records = archive_data.get("records", [])
                        if records:
                            # 标记数据来源为归档
                            from_source = "archive"
                        else:
                            from_source = "memory"
                    else:
                        from_source = "memory"
                else:
                    from_source = "memory" if records else "none"

                if not records:
                    return CanvasToolResult(
                        success=True,
                        content=json.dumps({"results": [], "message": f"No results found for drawing_session_id: {drawing_session_id}"}, ensure_ascii=False)
                    )
                if history:
                    return CanvasToolResult(
                        success=True,
                        content=json.dumps({"results": records, "source": from_source}, ensure_ascii=False)
                    )
                # 返回最新的
                record = records[-1]
                if field:
                    value = record.get(field) if isinstance(record, dict) else getattr(record, field, None)
                    return CanvasToolResult(
                        success=True,
                        content=json.dumps({field: value}, ensure_ascii=False)
                    )
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({"record": record, "source": from_source}, ensure_ascii=False)
                )

            # 按元素ID查询
            if element_id:
                records = self._store.get_by_element_id(element_id)
                if not records:
                    return CanvasToolResult(
                        success=True,
                        content=json.dumps({"results": [], "message": f"No results found for element_id: {element_id}"}, ensure_ascii=False)
                    )
                if history:
                    return CanvasToolResult(
                        success=True,
                        content=json.dumps({"results": [r.to_dict() for r in records]}, ensure_ascii=False)
                    )
                # 返回最新的
                record = records[-1]
                if field and record.result_data:
                    value = record.result_data.get(field)
                    return CanvasToolResult(
                        success=True,
                        content=json.dumps({field: value}, ensure_ascii=False)
                    )
                return CanvasToolResult(
                    success=True,
                    content=json.dumps(record.to_dict(), ensure_ascii=False)
                )

            # 返回历史列表
            if history:
                history_list = self._store.get_history(tool_name=tool_name, limit=20)
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({"history": history_list}, ensure_ascii=False)
                )

            # 获取特定字段
            if field:
                value = self._store.get_field(tool_name, field, index)
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({field: value}, ensure_ascii=False)
                )

            # 获取工具结果
            record = self._store.get_latest(tool_name=tool_name, index=index)
            if not record:
                return CanvasToolResult(
                    success=True,
                    content=json.dumps({"results": None, "message": f"No result found for tool: {tool_name}"}, ensure_ascii=False)
                )
            return CanvasToolResult(
                success=True,
                content=json.dumps(record.to_dict(), ensure_ascii=False)
            )

        except Exception as e:
            logger.error(f"GetCanvasToolResultTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"查询工具结果异常: {str(e)}")


class CanvasSnapshotTool(Tool):
    """
    画布视觉快照工具

    获取画布的视觉快照（低分辨率缩略图），让 Agent 能够"看到"当前画布的渲染效果。
    用于在绘制复杂图案前检查画布状态，或在绘制后验证效果。

    【使用场景】
    1. 绘制前检查：在开始复杂图案绘制前，先获取当前画布状态
    2. 绘制后验证：绘制完成后，验证实际渲染效果是否符合预期
    3. 迭代调整：根据视觉反馈，调整后续绘制策略
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator = None,
                 tool_result_store=None, canvas_id: str = None):
        self.canvas = canvas_core
        self.orchestrator = orchestrator
        self._tool_result_store = tool_result_store
        self._canvas_id = canvas_id or (canvas_core.canvas_id if canvas_core else None)

    @property
    def name(self) -> str:
        return "canvas_snapshot"

    @property
    def description(self) -> str:
        return """获取画布的视觉快照（低分辨率缩略图）。

让 Agent 能够"看到"当前画布的渲染效果，用于验证绘制结果或检查画布状态。
图片会自动上传到 OSS，生成公开可访问的 URL。

【返回数据】
- visual_snapshot_url: OSS 公开 URL（多模态模型可直接访问）
- visual_snapshot: base64 编码的低分辨率 PNG 图片（保留以兼容）
- canvas_info: 画布基本信息（尺寸、背景色）
- elements_summary: 当前画布上的元素摘要

【使用建议】
- 绘制复杂图案时，建议在每步操作后调用此工具
- 图片 URL 会自动传递给多模态模型进行分析
- 结合 canvas_draw 返回的 spatial_hints 和 element_full_attrs 进行精确定位

【重要】使用此工具前，请先激活 canvas_snapshot 技能获取详细说明。
激活技能：use_skill("canvas_snapshot")"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "thumbnail_size": {
                    "type": "string",
                    "enum": ["small", "medium", "large"],
                    "default": "medium",
                    "description": "缩略图尺寸：small(320px), medium(640px), large(1280px)"
                },
                "include_elements": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否包含元素详情摘要"
                },
                "upload_to_oss": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否上传到 OSS 生成公开 URL（默认 True，设为 False 则只返回 base64）"
                }
            },
        }

    async def execute(self, thumbnail_size: str = "medium",
                     include_elements: bool = True,
                     upload_to_oss: bool = True) -> CanvasToolResult:
        """
        获取画布视觉快照

        【自动获取选择区域】
        自动从画布获取当前矩形选择工具指定的区域（selection），
        只渲染该区域内的内容。

        Args:
            thumbnail_size: 缩略图尺寸
            include_elements: 是否包含元素详情
            upload_to_oss: 是否上传到 OSS 生成公开 URL（默认 True）

        Returns:
            CanvasToolResult: 包含 visual_snapshot_url 和画布信息
        """
        try:
            if not self.canvas:
                return CanvasToolResult(success=False, error="画布未初始化")

            # 获取画布快照
            snapshot = self.canvas.get_snapshot()

            # 【新增】自动获取当前选择区域
            selection_region = self.canvas.selection
            selection_bounds = None
            if selection_region and selection_region.bounds:
                selection_bounds = selection_region.bounds
                # 确保 bounds 有效
                if selection_bounds.get("width", 0) > 0 and selection_bounds.get("height", 0) > 0:
                    logger.info(f"[CanvasSnapshotTool] Using selection region: {selection_bounds}")
                else:
                    selection_bounds = None

            # 构建返回数据
            result_data = {
                "canvas_info": {
                    "canvas_id": snapshot.canvas_id,
                    "name": snapshot.name,
                    "width": snapshot.width,
                    "height": snapshot.height,
                    "background_color": snapshot.background_color,
                },
                "elements_count": len(snapshot.elements),
            }

            # 【新增】添加选择区域信息
            if selection_bounds:
                result_data["selection_info"] = {
                    "selection_id": selection_region.id if selection_region else None,
                    "selection_type": selection_region.type if selection_region else None,
                    "bounds": selection_bounds,
                    # 选择区域在原画布中的位置
                    "x": selection_bounds.get("x", 0),
                    "y": selection_bounds.get("y", 0),
                    "width": selection_bounds.get("width", 0),
                    "height": selection_bounds.get("height", 0),
                }
            else:
                result_data["selection_info"] = None

            # 生成视觉快照（base64 缩略图），传入选择区域
            visual_snapshot_base64 = await self._generate_visual_snapshot(
                snapshot, thumbnail_size, selection_bounds)

            # 【新增】上传到 OSS 生成公开 URL
            if upload_to_oss:
                try:
                    visual_snapshot_url = await self._upload_snapshot_to_oss(
                        visual_snapshot_base64, snapshot.canvas_id)
                    result_data["visual_snapshot_url"] = visual_snapshot_url
                    result_data["visual_snapshot"] = visual_snapshot_base64  # 保留 base64 以兼容
                    logger.info(f"[CanvasSnapshotTool] 上传到 OSS 成功: {visual_snapshot_url}")
                except Exception as e:
                    logger.warning(f"[CanvasSnapshotTool] OSS 上传失败，使用 base64: {e}")
                    result_data["visual_snapshot"] = visual_snapshot_base64
            else:
                result_data["visual_snapshot"] = visual_snapshot_base64

            # 添加元素摘要（只包含选择区域内的元素）
            if include_elements:
                elements_summary = self._build_elements_summary(snapshot, selection_bounds)
                result_data["elements_summary"] = elements_summary

            return CanvasToolResult(
                success=True,
                content=json.dumps(result_data, ensure_ascii=False)
            )

        except Exception as e:
            logger.error(f"CanvasSnapshotTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"获取快照异常: {str(e)}")

    async def _upload_snapshot_to_oss(self, base64_data: str, canvas_id: str = None) -> str:
        """
        将 base64 图片上传到 OSS 并返回公开 URL

        Args:
            base64_data: base64 编码的图片数据（不带 data:image 前缀）
            canvas_id: 画布 ID（用于生成文件名）

        Returns:
            公开可访问的 OSS URL
        """
        import base64
        import uuid

        try:
            # 解码 base64
            image_data = base64.b64decode(base64_data)

            # 获取 OSS 配置
            project_root = Path(__file__).parent.parent.parent
            import sys
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from agent.config.config_service import AgentConfigService
            config_service = AgentConfigService()
            env_config = config_service.get_environment_config()
            oss_config = env_config.get("oss", {})

            if not oss_config or not oss_config.get("access_key_id"):
                raise Exception("OSS 配置未找到")

            import oss2

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            canvas_prefix = f"{canvas_id[:8]}_" if canvas_id else ""
            filename = f"canvas_snapshot/{canvas_prefix}{timestamp}_{uuid.uuid4().hex[:8]}.png"

            access_key_id = oss_config["access_key_id"]
            access_key_secret = oss_config["access_key_secret"]
            bucket_name = oss_config["bucket"]
            endpoint = oss_config["endpoint"]

            auth = oss2.Auth(access_key_id, access_key_secret)
            bucket = oss2.Bucket(auth, endpoint, bucket_name)

            result = bucket.put_object(filename, image_data)
            if result.status != 200:
                raise Exception(f"OSS 上传失败: status={result.status}")

            public_url = f"https://{bucket_name}.{endpoint}/{filename}"
            logger.info(f"[CanvasSnapshotTool] 上传到 OSS 成功: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"[CanvasSnapshotTool] OSS 上传失败: {e}")
            raise

    async def _generate_visual_snapshot(self, snapshot, size: str,
                                       selection_bounds: Dict[str, float] = None) -> str:
        """
        生成视觉快照（base64 编码的缩略图）

        【选择区域支持】
        如果指定了 selection_bounds，则只渲染该区域内的内容，
        缩略图的尺寸比例与选择区域一致。

        Args:
            snapshot: CanvasSnapshot 对象
            size: 缩略图尺寸
            selection_bounds: 选择区域边界 {x, y, width, height}，如果为 None 则渲染整个画布

        Returns:
            base64 编码的 PNG 图片（不带 data:image/png;base64, 前缀）
        """
        try:
            # 根据 size 确定缩略图尺寸
            size_map = {
                "small": (320, 240),
                "medium": (640, 480),
                "large": (1280, 960),
            }
            max_width, max_height = size_map.get(size, (640, 480))

            # 【修改】如果指定了选择区域，使用选择区域的尺寸
            if selection_bounds:
                render_width = selection_bounds.get("width", snapshot.width)
                render_height = selection_bounds.get("height", snapshot.height)
                offset_x = selection_bounds.get("x", 0)
                offset_y = selection_bounds.get("y", 0)
            else:
                render_width = snapshot.width
                render_height = snapshot.height
                offset_x = 0
                offset_y = 0

            # 计算缩放比例
            scale_x = max_width / render_width if render_width > max_width else 1
            scale_y = max_height / render_height if render_height > max_height else 1
            scale = min(scale_x, scale_y)

            thumb_width = int(render_width * scale)
            thumb_height = int(render_height * scale)

            # 使用 PIL 生成缩略图
            from PIL import Image as PILImage, ImageDraw

            # 创建缩略图
            img = PILImage.new("RGB", (thumb_width, thumb_height),
                              self._hex_to_rgb(snapshot.background_color or "#ffffff"))
            draw = ImageDraw.Draw(img)

            # 【修改】绘制每个元素，只绘制在选择区域内的
            for element in snapshot.elements:
                if not element.visible:
                    continue

                # 如果有选择区域，检查元素是否在选择区域内
                if selection_bounds:
                    elem_bounds = element.get_bounds()
                    if not self._is_element_in_selection(elem_bounds, selection_bounds):
                        continue

                self._draw_element_simplified(draw, element, scale, offset_x, offset_y)

            # 编码为 base64
            import base64
            import io

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

            return base64_data

        except ImportError:
            logger.warning("PIL not available, using placeholder snapshot")
            return self._generate_placeholder_snapshot(snapshot, selection_bounds)
        except Exception as e:
            logger.error(f"Failed to generate visual snapshot: {e}")
            return self._generate_placeholder_snapshot(snapshot, selection_bounds)

    def _is_element_in_selection(self, elem_bounds: Dict[str, float],
                                  selection_bounds: Dict[str, float]) -> bool:
        """检查元素是否在选择区域内"""
        if not elem_bounds or not selection_bounds:
            return True  # 无法判断时默认包含

        # 元素边界
        elem_left = elem_bounds.get("x", 0)
        elem_top = elem_bounds.get("y", 0)
        elem_right = elem_left + elem_bounds.get("width", 0)
        elem_bottom = elem_top + elem_bounds.get("height", 0)

        # 选择区域边界
        sel_left = selection_bounds.get("x", 0)
        sel_top = selection_bounds.get("y", 0)
        sel_right = sel_left + selection_bounds.get("width", 0)
        sel_bottom = sel_top + selection_bounds.get("height", 0)

        # 检查是否有交集
        return not (elem_right < sel_left or elem_left > sel_right or
                    elem_bottom < sel_top or elem_top > sel_bottom)

    def _draw_element_simplified(self, draw,
                                  element, scale: float,
                                  offset_x: float = 0, offset_y: float = 0):
        """简化绘制元素到缩略图

        Args:
            draw: PIL ImageDraw 对象
            element: CanvasElement 对象
            scale: 缩放比例
            offset_x: 选择区域在原画布中的 X 偏移（渲染时需要减去）
            offset_y: 选择区域在原画布中的 Y 偏移（渲染时需要减去）
        """
        try:
            # 获取元素边界
            bounds = element.get_bounds()
            # 【修改】减去偏移量，使坐标相对于选择区域
            x = int((bounds["x"] - offset_x) * scale)
            y = int((bounds["y"] - offset_y) * scale)
            w = int(bounds["width"] * scale)
            h = int(bounds["height"] * scale)

            if w <= 0 or h <= 0:
                return

            # 获取样式
            fill = element.styles.fill if element.styles else None
            stroke = element.styles.stroke if element.styles else None
            stroke_width = int(element.styles.stroke_width * scale) if element.styles else 1

            # 转换颜色
            fill_color = self._hex_to_rgb(fill) if fill else None
            stroke_color = self._hex_to_rgb(stroke) if stroke else None

            # 绘制
            if element.type == "shape":
                # 根据 shape_type 绘制不同形状
                shape_type = element.metadata.shape_type if element.metadata else "rectangle"
                if shape_type == "ellipse":
                    draw.ellipse([x, y, x + w, y + h],
                                fill=fill_color, outline=stroke_color)
                else:
                    draw.rectangle([x, y, x + w, y + h],
                                  fill=fill_color, outline=stroke_color)
            elif element.type == "image":
                # 图片用灰色矩形占位
                draw.rectangle([x, y, x + w, y + h],
                              fill=(200, 200, 200), outline=(100, 100, 100))
            elif element.type == "text":
                # 文本用下划线矩形占位
                draw.rectangle([x, y, x + w, y + h],
                              fill=(240, 240, 220), outline=(100, 100, 100))
            else:
                # 默认绘制矩形边框
                draw.rectangle([x, y, x + w, y + h],
                              fill=fill_color, outline=stroke_color)

        except Exception as e:
            logger.debug(f"Failed to draw element {element.id}: {e}")

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """将十六进制颜色转换为 RGB 元组"""
        if not hex_color:
            return (0, 0, 0)
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        elif len(hex_color) == 3:
            return tuple(int(c * 2, 16) for c in hex_color)
        return (0, 0, 0)

    def _generate_placeholder_snapshot(self, snapshot,
                                      selection_bounds: Dict[str, float] = None) -> str:
        """生成占位符快照（当无法渲染时）"""
        import base64
        import io
        from PIL import Image as PILImage, ImageDraw

        # 如果有选择区域，使用选择区域的尺寸
        if selection_bounds:
            width, height = 320, 240
            label = f"Selection: {selection_bounds.get('width', 0):.0f}x{selection_bounds.get('height', 0):.0f}"
        else:
            width, height = 320, 240
            label = f"Canvas: {snapshot.width}x{snapshot.height}"

        img = PILImage.new("RGB", (width, height), (250, 250, 250))
        draw = ImageDraw.Draw(img)

        # 绘制边框和提示文字
        draw.rectangle([0, 0, width - 1, height - 1], outline=(200, 200, 200))
        draw.text((10, height // 2), label, fill=(100, 100, 100))

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _build_elements_summary(self, snapshot,
                                selection_bounds: Dict[str, float] = None) -> Dict[str, Any]:
        """构建元素摘要（只包含选择区域内的元素）"""
        # 过滤只在选择区域内的元素
        if selection_bounds:
            filtered_elements = [
                e for e in snapshot.elements
                if e.visible and self._is_element_in_selection(e.get_bounds(), selection_bounds)
            ]
        else:
            filtered_elements = snapshot.elements

        summary = {
            "total": len(filtered_elements),
            "by_type": {},
            "top_elements": []
        }

        # 按类型统计
        for element in filtered_elements:
            elem_type = element.type
            if elem_type not in summary["by_type"]:
                summary["by_type"][elem_type] = 0
            summary["by_type"][elem_type] += 1

        # 获取最上面的几个元素（按 z_index）
        sorted_elements = sorted(filtered_elements,
                               key=lambda e: e.z_index,
                               reverse=True)
        for elem in sorted_elements[:5]:
            bounds = elem.get_bounds()
            summary["top_elements"].append({
                "id": elem.id,
                "type": elem.type,
                "bounds": bounds,
                "position": elem.position,
                "size": elem.size,
            })

        return summary


class CanvasShapeTool(Tool):
    """
    画板形状工具 - 使用预定义形状进行绘制

    提供常用的几何形状（星形、心形、箭头、三角形等），
    无需手动计算 SVG path，直接指定形状类型即可绘制。

    【支持的形状】
    - star: 五角星
    - heart: 心形
    - triangle: 三角形
    - arrow: 箭头
    - diamond: 菱形
    - hexagon: 六边形
    - pentagon: 五边形
    - cross: 十字形
    - circle: 圆形
    - ellipse: 椭圆
    - rect: 矩形
    """

    # 支持的形状列表
    SHAPE_TYPES = [
        "star", "heart", "triangle", "arrow", "diamond",
        "hexagon", "pentagon", "cross", "circle", "ellipse", "rect"
    ]

    def __init__(self, canvas_core, orchestrator: Optional[Any] = None,
                 session_id: str = None, tool_result_store=None):
        self.canvas = canvas_core
        self.orchestrator = orchestrator
        self.session_id = session_id
        self.progress_callback = None
        self._tool_result_store = tool_result_store
        self._drawing_session_count: int = 0
        self._current_drawing_session_id: Optional[str] = None
        self._drawing_session_lock: asyncio.Lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "canvas_shape"

    @property
    def description(self) -> str:
        shapes = ", ".join(self.SHAPE_TYPES)
        return f"""在画板指定区域绘制预定义形状。

支持以下形状：{shapes}

【参数说明】
- shape_type: 形状类型（必选）
- color: 描边颜色
- stroke_width: 线条粗细
- fill_color: 填充颜色（可选）
- scale: 图形大小比例 (0.0-1.0)
- offset_x: 横向偏移比例 (-0.5 到 0.5)
- offset_y: 纵向偏移比例 (-0.5 到 0.5)

【重要】使用此工具前，请先激活 canvas_draw 技能获取完整说明。
激活技能：use_skill("canvas_draw")"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "shape_type": {
                    "type": "string",
                    "enum": self.SHAPE_TYPES,
                    "description": f"形状类型，可选值：{', '.join(self.SHAPE_TYPES)}"
                },
                "color": {
                    "type": "string",
                    "description": "描边颜色（支持颜色名称或 HEX 值）",
                    "default": "#000000"
                },
                "stroke_width": {
                    "type": "number",
                    "description": "线条粗细",
                    "default": 2
                },
                "fill_color": {
                    "type": "string",
                    "description": "填充颜色（可选，不指定则不填充）"
                },
                "scale": {
                    "type": "number",
                    "description": "图形大小比例 (0.0-1.0)，默认 1.0",
                    "default": 1.0
                },
                "offset_x": {
                    "type": "number",
                    "description": "横向偏移比例 (-0.5 到 0.5)，默认 0",
                    "default": 0.0
                },
                "offset_y": {
                    "type": "number",
                    "description": "纵向偏移比例 (-0.5 到 0.5)，默认 0",
                    "default": 0.0
                },
                "drawing_session_id": {
                    "type": "string",
                    "description": "绘图会话ID（用于关联同一图案的多次绘制）"
                }
            },
            "required": ["shape_type"]
        }

    async def execute(
        self,
        shape_type: str,
        color: str = "#000000",
        stroke_width: float = 2,
        fill_color: Optional[str] = None,
        scale: float = 1.0,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        drawing_session_id: Optional[str] = None
    ) -> CanvasToolResult:
        """执行形状绘制"""
        try:
            from ..canvas.canvas_core import CanvasElement, ElementMetadata, ElementStyles, ElementType

            # 获取选择区域
            selection_bounds = self._get_current_selection_bounds()
            if not selection_bounds:
                return CanvasToolResult(success=False,
                                      error="请先使用框选工具选择区域")

            # 处理会话
            async with self._drawing_session_lock:
                if drawing_session_id:
                    self._current_drawing_session_id = drawing_session_id
                    self._drawing_session_count += 1
                elif self._drawing_session_count == 0:
                    self._current_drawing_session_id = str(uuid.uuid4())[:8]
                    self._drawing_session_count = 1
                else:
                    self._drawing_session_count += 1

            # 颜色转换
            stroke_color = self._ensure_hex_color(color)
            fill_color_hex = self._ensure_hex_color(fill_color) if fill_color else None

            # 计算绘制边界
            x, y = selection_bounds["x"], selection_bounds["y"]
            w, h = selection_bounds.get("width", 100), selection_bounds.get("height", 100)

            # 应用缩放和偏移
            offset_pixel_x = w * offset_x
            offset_pixel_y = h * offset_y
            scaled_w = w * scale
            scaled_h = h * scale

            # 生成形状路径点
            if shape_type == "heart":
                # 心形使用多边形公式
                points = self._generate_heart_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "circle":
                points = self._generate_circle_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "ellipse":
                points = self._generate_ellipse_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "rect":
                points = self._generate_rect_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "star":
                points = self._generate_star_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "triangle":
                points = self._generate_triangle_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "arrow":
                points = self._generate_arrow_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "diamond":
                points = self._generate_diamond_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "hexagon":
                points = self._generate_hexagon_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            elif shape_type == "pentagon":
                points = self._generate_polygon_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y, 5)
            elif shape_type == "cross":
                points = self._generate_cross_points(
                    x, y, scaled_w, scaled_h, offset_pixel_x, offset_pixel_y)
            else:
                return CanvasToolResult(success=False, error=f"不支持的形状类型: {shape_type}")

            # 计算实际边界
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            actual_bounds = {
                "x": min(xs),
                "y": min(ys),
                "width": max(xs) - min(xs),
                "height": max(ys) - min(ys)
            }

            # 创建元素
            element_id = str(uuid.uuid4())
            element = CanvasElement(
                id=element_id,
                type=ElementType.SHAPE.value,
                position={"x": actual_bounds["x"], "y": actual_bounds["y"]},
                size={"width": actual_bounds["width"], "height": actual_bounds["height"]},
                metadata=ElementMetadata(
                    shape_type="path",
                    points=points,
                    stroke_color=stroke_color,
                    stroke_width=stroke_width,
                    fill_color=fill_color_hex
                ),
                styles=ElementStyles(
                    x=actual_bounds["x"],
                    y=actual_bounds["y"],
                    width=actual_bounds["width"],
                    height=actual_bounds["height"],
                    fill=fill_color_hex,
                    stroke=stroke_color,
                    stroke_width=stroke_width
                ),
                created_by="agent"
            )

            # 添加到画布
            success = await self.canvas.add_element(element)

            if success:
                # 构建返回结果
                # 【新增】构建 element_full_attrs
                element_full_attrs = self._build_element_full_attrs(element, actual_bounds)

                # 【新增】构建 spatial_hints
                spatial_hints = self._build_spatial_hints(element, actual_bounds)

                return CanvasToolResult(
                    success=True,
                    content=json.dumps({
                        "element_id": element_id,
                        "shape_type": shape_type,
                        "bounds": actual_bounds,
                        "element_position": element.position,
                        "element_size": element.size,
                        "element_data": element.to_dict(),
                        "element_full_attrs": element_full_attrs,
                        "spatial_hints": spatial_hints,
                        "drawing_session_id": self._current_drawing_session_id,
                    }, ensure_ascii=False)
                )

            return CanvasToolResult(success=False, error="添加元素失败")

        except Exception as e:
            logger.error(f"CanvasShapeTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"绘制形状异常: {str(e)}")

    def _ensure_hex_color(self, color: str) -> str:
        """确保颜色是有效的 HEX 格式"""
        if not color:
            return "#000000"

        # 如果已经是 HEX 格式
        if color.startswith("#"):
            return color

        # 颜色名称映射
        color_map = {
            "red": "#FF0000",
            "green": "#00FF00",
            "blue": "#0000FF",
            "yellow": "#FFFF00",
            "cyan": "#00FFFF",
            "magenta": "#FF00FF",
            "white": "#FFFFFF",
            "black": "#000000",
            "gray": "#808080",
            "grey": "#808080",
            "orange": "#FFA500",
            "purple": "#800080",
            "pink": "#FFC0CB",
            "brown": "#A52A2A",
        }
        return color_map.get(color.lower(), "#000000")

    def _get_current_selection_bounds(self) -> Optional[Dict[str, float]]:
        """获取当前选择区域"""
        if self.canvas and self.canvas._current_selection:
            bounds = self.canvas._current_selection.bounds
            if bounds and bounds.get("width", 0) > 0 and bounds.get("height", 0) > 0:
                return bounds
        return None

    # ===== 形状生成方法 =====

    def _generate_heart_points(self, x: float, y: float, w: float, h: float,
                                 offset_x: float, offset_y: float) -> List[List[float]]:
        """生成心形路径点"""
        heart_points = []
        scale_factor = min(w, h) / 32
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        for i in range(37):
            t = i * 10 * math.pi / 180
            hx = 16 * math.sin(t) ** 3
            hy = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
            px = cx + hx * scale_factor
            py = cy + hy * scale_factor
            heart_points.append([px, py])
        return heart_points

    def _generate_circle_points(self, x: float, y: float, w: float, h: float,
                                 offset_x: float, offset_y: float) -> List[List[float]]:
        """生成圆形路径点"""
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        radius = min(w, h) / 2
        points = []
        for i in range(37):
            angle = i * 10 * math.pi / 180
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            points.append([px, py])
        return points

    def _generate_ellipse_points(self, x: float, y: float, w: float, h: float,
                                  offset_x: float, offset_y: float) -> List[List[float]]:
        """生成椭圆路径点"""
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        rx, ry = w / 2, h / 2
        points = []
        for i in range(37):
            angle = i * 10 * math.pi / 180
            px = cx + rx * math.cos(angle)
            py = cy + ry * math.sin(angle)
            points.append([px, py])
        return points

    def _generate_rect_points(self, x: float, y: float, w: float, h: float,
                               offset_x: float, offset_y: float) -> List[List[float]]:
        """生成矩形路径点"""
        rx = x + offset_x
        ry = y + offset_y
        return [
            [rx, ry],
            [rx + w, ry],
            [rx + w, ry + h],
            [rx, ry + h],
            [rx, ry]
        ]

    def _generate_star_points(self, x: float, y: float, w: float, h: float,
                               offset_x: float, offset_y: float) -> List[List[float]]:
        """生成五角星路径点"""
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        outer_radius = min(w, h) / 2
        inner_radius = outer_radius * 0.382
        points = []
        for i in range(10):
            angle = (i * 36 - 90) * math.pi / 180
            radius = outer_radius if i % 2 == 0 else inner_radius
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            points.append([px, py])
        points.append(points[0])
        return points

    def _generate_triangle_points(self, x: float, y: float, w: float, h: float,
                                   offset_x: float, offset_y: float) -> List[List[float]]:
        """生成三角形路径点"""
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        return [
            [cx, y + offset_y],
            [x + w + offset_x, y + h + offset_y],
            [x + offset_x, y + h + offset_y],
            [cx, y + offset_y]
        ]

    def _generate_arrow_points(self, x: float, y: float, w: float, h: float,
                                offset_x: float, offset_y: float) -> List[List[float]]:
        """生成箭头路径点"""
        arrow_head_ratio = 0.3
        shaft_ratio = 0.4
        arrow_head_w = w * arrow_head_ratio
        shaft_h = h * shaft_ratio
        shaft_w = w * 0.15
        cx = x + w / 2 + offset_x
        arrow_top = y + (h - shaft_h) / 2 + offset_y
        arrow_bottom = y + h - (h - shaft_h) / 2 + offset_y
        return [
            [cx, y + offset_y],
            [cx + arrow_head_w / 2, y + h * arrow_head_ratio + offset_y],
            [cx + shaft_w / 2, arrow_top],
            [cx + shaft_w / 2, arrow_bottom],
            [cx + arrow_head_w / 2, arrow_bottom],
            [cx + arrow_head_w / 2, y + h + offset_y],
            [cx - arrow_head_w / 2, y + h + offset_y],
            [cx - arrow_head_w / 2, arrow_bottom],
            [cx - shaft_w / 2, arrow_bottom],
            [cx - shaft_w / 2, arrow_top],
            [cx - arrow_head_w / 2, arrow_top],
            [cx - arrow_head_w / 2, y + h * arrow_head_ratio + offset_y],
            [cx, y + offset_y]
        ]

    def _generate_diamond_points(self, x: float, y: float, w: float, h: float,
                                  offset_x: float, offset_y: float) -> List[List[float]]:
        """生成菱形路径点"""
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        return [
            [cx, y + offset_y],
            [x + w + offset_x, cy],
            [cx, y + h + offset_y],
            [x + offset_x, cy],
            [cx, y + offset_y]
        ]

    def _generate_hexagon_points(self, x: float, y: float, w: float, h: float,
                                  offset_x: float, offset_y: float) -> List[List[float]]:
        """生成六边形路径点"""
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        radius = min(w, h) / 2
        points = []
        for i in range(6):
            angle = (i * 60 - 90) * math.pi / 180
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            points.append([px, py])
        points.append(points[0])
        return points

    def _generate_polygon_points(self, x: float, y: float, w: float, h: float,
                                  offset_x: float, offset_y: float, sides: int) -> List[List[float]]:
        """生成正多边形路径点"""
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        radius = min(w, h) / 2
        points = []
        for i in range(sides):
            angle = (i * 360 / sides - 90) * math.pi / 180
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            points.append([px, py])
        points.append(points[0])
        return points

    def _generate_cross_points(self, x: float, y: float, w: float, h: float,
                               offset_x: float, offset_y: float) -> List[List[float]]:
        """生成十字形路径点"""
        arm_ratio = 0.35
        arm_w = w * arm_ratio
        arm_h = h * arm_ratio
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        return [
            [cx - arm_w / 2, cy - arm_h / 2],
            [cx + arm_w / 2, cy - arm_h / 2],
            [cx + arm_w / 2, y + offset_y],
            [cx + w / 2, y + offset_y],
            [cx + w / 2, cy - arm_h / 2],
            [cx + arm_w / 2 + (w - arm_w) / 2, cy - arm_h / 2],
            [cx + arm_w / 2 + (w - arm_w) / 2, cy + arm_h / 2],
            [cx + w / 2, cy + arm_h / 2],
            [cx + w / 2, y + h + offset_y],
            [cx + arm_w / 2, y + h + offset_y],
            [cx + arm_w / 2, cy + arm_h / 2],
            [cx - arm_w / 2, cy + arm_h / 2],
            [cx - arm_w / 2, y + h + offset_y],
            [cx - w / 2, y + h + offset_y],
            [cx - w / 2, cy + arm_h / 2],
            [cx - arm_w / 2 - (w - arm_w) / 2, cy + arm_h / 2],
            [cx - arm_w / 2 - (w - arm_w) / 2, cy - arm_h / 2],
            [cx - w / 2, cy - arm_h / 2],
            [cx - w / 2, y + offset_y],
            [cx - arm_w / 2, y + offset_y],
            [cx - arm_w / 2, cy - arm_h / 2],
        ]

    # ===== 辅助方法：构建完整元素属性和空间感知 =====

    def _build_element_full_attrs(self, element, bounds: Dict[str, float]) -> Dict[str, Any]:
        """构建完整元素属性（增强版）"""
        attrs = element.to_dict()

        x = bounds["x"]
        y = bounds["y"]
        width = bounds["width"]
        height = bounds["height"]

        attrs["computed"] = {
            "center_x": x + width / 2,
            "center_y": y + height / 2,
            "right_edge_x": x + width,
            "bottom_edge_y": y + height,
            "left_edge": x,
            "right_edge": x + width,
            "top_edge": y,
            "bottom_edge": y + height,
        }

        if element.styles:
            attrs["styles_summary"] = {
                "fill": element.styles.fill,
                "stroke": element.styles.stroke,
                "stroke_width": element.styles.stroke_width,
                "opacity": element.styles.opacity,
                "rotation": element.styles.rotation,
            }

        return attrs

    def _build_spatial_hints(self, element, bounds: Dict[str, float]) -> Dict[str, Any]:
        """构建空间感知信息"""
        spatial_hints = {
            "aligned_with": [],
            "distance_to_nearest_edge": None,
        }

        if not self.canvas or not self.canvas._elements:
            return spatial_hints

        try:
            current_left = bounds["x"]
            current_right = bounds["x"] + bounds["width"]
            current_top = bounds["y"]
            current_bottom = bounds["y"] + bounds["height"]

            other_elements = []
            for elem_id, elem in self.canvas._elements.items():
                if elem_id == element.id:
                    continue
                if not elem.visible:
                    continue
                elem_bounds = elem.get_bounds()
                other_elements.append({
                    "id": elem_id,
                    "type": elem.type,
                    "bounds": elem_bounds,
                })

            if not other_elements:
                return spatial_hints

            min_distance = float("inf")
            nearest_edge_info = None
            alignment_tolerance = 5

            for other in other_elements:
                other_bounds = other["bounds"]
                other_left = other_bounds["x"]
                other_right = other_bounds["x"] + other_bounds["width"]
                other_top = other_bounds["y"]
                other_bottom = other_bounds["y"] + other_bounds["height"]
                other_id = other["id"]

                # 检测边缘对齐
                if abs(current_left - other_left) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.left")
                elif abs(current_right - other_right) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.right")
                elif abs(current_left - other_right) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.right_edge")
                elif abs(current_right - other_left) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.left_edge")

                if abs(current_top - other_top) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.top")
                elif abs(current_bottom - other_bottom) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.bottom")
                elif abs(current_top - other_bottom) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.bottom_edge")
                elif abs(current_bottom - other_top) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.top_edge")

                # 检测中心点对齐
                current_center_x = current_left + bounds["width"] / 2
                other_center_x = other_left + other_bounds["width"] / 2
                if abs(current_center_x - other_center_x) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.center_x")

                current_center_y = current_top + bounds["height"] / 2
                other_center_y = other_top + other_bounds["height"] / 2
                if abs(current_center_y - other_center_y) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.center_y")

                # 计算距离
                if current_right < other_left:
                    horiz_dist = other_left - current_right
                elif current_left > other_right:
                    horiz_dist = current_left - other_right
                else:
                    horiz_dist = 0

                if current_bottom < other_top:
                    vert_dist = other_top - current_bottom
                elif current_top > other_bottom:
                    vert_dist = current_top - other_bottom
                else:
                    vert_dist = 0

                distance = horiz_dist + vert_dist

                if distance > 0 and distance < min_distance:
                    min_distance = distance
                    nearest_edge_info = {
                        "distance": min_distance,
                        "direction": self._get_distance_direction(
                            current_left, current_right, current_top, current_bottom,
                            other_left, other_right, other_top, other_bottom
                        )
                    }

            if nearest_edge_info:
                spatial_hints["distance_to_nearest_edge"] = nearest_edge_info["distance"]
                spatial_hints["nearest_edge_direction"] = nearest_edge_info["direction"]

        except Exception as e:
            logger.warning(f"[CanvasShapeTool] Failed to build spatial hints: {e}")

        return spatial_hints

    def _get_distance_direction(self,
                                cur_left: float, cur_right: float,
                                cur_top: float, cur_bottom: float,
                                oth_left: float, oth_right: float,
                                oth_top: float, oth_bottom: float) -> str:
        """计算当前元素到目标元素的距离方向"""
        directions = []

        if cur_right <= oth_left:
            directions.append("right")
        elif cur_left >= oth_right:
            directions.append("left")

        if cur_bottom <= oth_top:
            directions.append("below")
        elif cur_top >= oth_bottom:
            directions.append("above")

        return "-".join(directions) if directions else "overlapping"


class CanvasUndoTool(Tool):
    """
    回撤工具 - 回撤 Agent 最近一次绘制操作

    当 Agent 发现之前的绘制结果不符合预期（如颜色、位置、大小错误）时，
    可以使用此工具回撤上一次的绘制，然后重新绘制。

    【机制说明】
    - 本工具模拟人类绘画时的"橡皮擦"功能
    - 回撤后会从存储区移除该记录，并通知前端删除对应元素
    - Agent 的回撤只影响自己绘制的内容，不影响用户绘制的内容
    - 回撤后，Agent 可以重新调用 canvas_draw 进行正确的绘制
    """

    def __init__(self, canvas_core, orchestrator: Orchestrator = None,
                 tool_result_store=None, canvas_id: str = None):
        self.canvas = canvas_core
        self.orchestrator = orchestrator
        self._tool_result_store = tool_result_store
        self._canvas_id = canvas_id or (canvas_core.canvas_id if canvas_core else None)
        self._progress_callback = None

    @property
    def name(self) -> str:
        return "canvas_undo"

    @property
    def description(self) -> str:
        return """回撤 Agent 的绘制操作（类似橡皮擦）。

当发现之前的绘制结果有问题时使用此工具回撤。

【支持两种模式】
1. 不指定 drawing_session_id：回撤最近一次绘制操作
2. 指定 drawing_session_id：回撤该图案会话的所有绘制操作

【重要】使用此工具前，请先激活 canvas_undo 技能获取完整的回撤机制说明。
激活技能：use_skill("canvas_undo")"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "回撤原因（可选），如'颜色不对'、'位置偏移'等"
                },
                "drawing_session_id": {
                    "type": "string",
                    "description": "图案会话ID（可选）。指定后回撤该图案的所有绘制操作。不指定则回撤最近一次绘制。"
                }
            },
            "required": []
        }

    async def execute(
        self,
        reason: Optional[str] = None,
        drawing_session_id: Optional[str] = None,
    ) -> CanvasToolResult:
        """
        执行回撤操作

        Args:
            reason: 回撤原因
            drawing_session_id: 图案会话ID（可选）
                - 指定时：回撤该图案的所有绘制操作
                - 不指定时：回撤最近一次绘制操作
        """
        try:
            # 检查是否有可回撤的记录
            if not self._tool_result_store:
                return CanvasToolResult(
                    success=False,
                    error="回撤工具未初始化，无法访问存储"
                )

            # 指定了 drawing_session_id，回撤该图案的所有绘制
            if drawing_session_id:
                return await self._undo_by_session(drawing_session_id, reason)

            # 未指定 drawing_session_id，回撤最近一次绘制
            return await self._undo_latest(reason)

        except Exception as e:
            logger.error(f"CanvasUndoTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"回撤异常: {str(e)}")

    async def _undo_by_session(self, drawing_session_id: str, reason: Optional[str]) -> CanvasToolResult:
        """按 drawing_session_id 回撤所有相关绘制"""
        # 获取该会话的所有 canvas_draw 记录
        session_records = self._tool_result_store.get_by_drawing_session(drawing_session_id)

        if not session_records:
            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "message": f"没有找到 drawing_session_id={drawing_session_id} 的绘制记录",
                    "undone": False,
                    "drawing_session_id": drawing_session_id
                }, ensure_ascii=False)
            )

        # 收集所有 element_id
        undone_element_ids = []
        for record in session_records:
            element_id = record.element_id
            if not element_id and record.result_data:
                element_id = record.result_data.get("element_id")
            if element_id:
                undone_element_ids.append(element_id)

        # 从存储中移除该会话的所有记录
        for _ in session_records:
            self._tool_result_store.pop_by_tool_name("canvas_draw")

        # 后端：同步删除 CanvasCore 中的所有元素
        if undone_element_ids and self.canvas:
            try:
                delete_success = await self.canvas.delete_elements(undone_element_ids)
                logger.info(f"[CanvasUndoTool] Backend delete_elements result: {delete_success}")
            except Exception as e:
                logger.error(f"[CanvasUndoTool] Failed to delete elements {undone_element_ids} from canvas: {e}")

        # 广播 DRAW_UNDO 消息给前端
        logger.info(f"[CanvasUndoTool] Broadcasting DRAW_UNDO for session: drawing_session_id={drawing_session_id}, elements={undone_element_ids}")
        if undone_element_ids and self._canvas_id:
            from ..api.canvas_routes import broadcast_to_canvas
            await broadcast_to_canvas(self._canvas_id, {
                "type": "DRAW_UNDO",
                "data": {
                    "element_ids": undone_element_ids,
                    "drawing_session_id": drawing_session_id,
                    "reason": reason or "未指定"
                }
            })
            logger.info(f"[CanvasUndoTool] DRAW_UNDO broadcast sent for {len(undone_element_ids)} elements")

        return CanvasToolResult(
            success=True,
            content=json.dumps({
                "message": f"已回撤 drawing_session_id={drawing_session_id} 的 {len(undone_element_ids)} 个绘制操作",
                "undone": True,
                "undone_element_ids": undone_element_ids,
                "drawing_session_id": drawing_session_id,
                "reason": reason or "未指定"
            }, ensure_ascii=False)
        )

    async def _undo_latest(self, reason: Optional[str]) -> CanvasToolResult:
        """回撤最近一次绘制"""
        # 获取最新的 canvas_draw 记录
        latest_record = self._tool_result_store.get_latest(tool_name="canvas_draw", index=-1)
        if not latest_record:
            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "message": "没有可回撤的绘制记录",
                    "undone": False
                }, ensure_ascii=False)
            )

        # 获取 element_id（最新的 canvas_draw 记录）
        undone_element_id = latest_record.element_id if latest_record.element_id else None
        if not undone_element_id and latest_record.result_data:
            undone_element_id = latest_record.result_data.get("element_id")

        # 使用 pop_by_tool_name 移除最新的 canvas_draw 记录
        removed = self._tool_result_store.pop_by_tool_name("canvas_draw")
        if not removed:
            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "message": "回撤失败，无法移除记录",
                    "undone": False
                }, ensure_ascii=False)
            )

        # 后端：同步删除 CanvasCore 中的实际元素
        if undone_element_id and self.canvas:
            try:
                delete_success = await self.canvas.delete_elements([undone_element_id])
                logger.info(f"[CanvasUndoTool] Backend delete_elements result: {delete_success}")
            except Exception as e:
                logger.error(f"[CanvasUndoTool] Failed to delete element {undone_element_id} from canvas: {e}")

        # 广播删除元素的消息给前端
        logger.info(f"[CanvasUndoTool] Broadcasting DRAW_UNDO: undone_element_id={undone_element_id}, _canvas_id={self._canvas_id}")
        if undone_element_id and self._canvas_id:
            from ..api.canvas_routes import broadcast_to_canvas
            await broadcast_to_canvas(self._canvas_id, {
                "type": "DRAW_UNDO",
                "data": {
                    "element_id": undone_element_id,
                    "reason": reason or "未指定"
                }
            })
            logger.info(f"[CanvasUndoTool] DRAW_UNDO broadcast sent")
        else:
            logger.warning(f"[CanvasUndoTool] DRAW_UNDO not broadcast: undone_element_id={undone_element_id}, _canvas_id={self._canvas_id}")

        return CanvasToolResult(
            success=True,
            content=json.dumps({
                "message": f"已回撤操作，删除了元素 {undone_element_id}",
                "undone": True,
                "undone_element_id": undone_element_id,
                "reason": reason or "未指定"
            }, ensure_ascii=False)
        )


class CanvasTransformTool(Tool):
    """
    画板变换工具 - 对已有元素进行变换操作

    支持的变换操作：
    - rotate: 旋转 (90/180/270度)
    - flip: 镜像 (horizontal/vertical)
    - scale: 缩放
    - duplicate: 复制到新位置
    - bring_to_front: 置顶
    - send_to_back: 置底
    - move_up: 上移一层
    - move_down: 下移一层
    """

    def __init__(self, canvas_core, orchestrator: Optional[Any] = None,
                 tool_result_store=None, canvas_id: str = None):
        self.canvas = canvas_core
        self.orchestrator = orchestrator
        self._tool_result_store = tool_result_store
        self._canvas_id = canvas_id or (canvas_core.canvas_id if canvas_core else None)

    @property
    def name(self) -> str:
        return "canvas_transform"

    @property
    def description(self) -> str:
        return """对画布上的元素进行变换操作。

【支持的变换操作】
- rotate: 旋转 (90/180/270度)
- flip: 镜像 (horizontal/vertical)
- scale: 缩放
- duplicate: 复制到新位置
- bring_to_front: 置顶
- send_to_back: 置底
- move_up: 上移一层
- move_down: 下移一层

【重要】使用此工具前，请先激活 canvas_draw 技能获取详细说明。
激活技能：use_skill("canvas_draw")"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["rotate", "flip", "scale", "duplicate",
                            "bring_to_front", "send_to_back", "move_up", "move_down"],
                    "description": "变换操作类型"
                },
                "element_id": {
                    "type": "string",
                    "description": "目标元素ID"
                },
                "degrees": {
                    "type": "number",
                    "enum": [90, 180, 270],
                    "description": "旋转角度（用于 rotate 操作）",
                    "default": 90
                },
                "flip_direction": {
                    "type": "string",
                    "enum": ["horizontal", "vertical"],
                    "description": "镜像方向（用于 flip 操作）",
                    "default": "horizontal"
                },
                "scale_factor": {
                    "type": "number",
                    "description": "缩放比例（用于 scale 操作，如 1.5 表示放大到1.5倍）",
                    "default": 1.0
                },
                "offset_x": {
                    "type": "number",
                    "description": "复制或移动后的横向偏移（像素）",
                    "default": 0
                },
                "offset_y": {
                    "type": "number",
                    "description": "复制或移动后的纵向偏移（像素）",
                    "default": 0
                }
            },
            "required": ["operation", "element_id"]
        }

    async def execute(
        self,
        operation: str,
        element_id: str,
        degrees: int = 90,
        flip_direction: str = "horizontal",
        scale_factor: float = 1.0,
        offset_x: float = 0,
        offset_y: float = 0
    ) -> CanvasToolResult:
        """执行变换操作"""
        try:
            # 获取目标元素
            element = self.canvas.get_element(element_id)
            if not element:
                return CanvasToolResult(
                    success=False,
                    error=f"未找到元素 {element_id}"
                )

            # 根据操作类型执行变换
            if operation == "rotate":
                return await self._rotate_element(element, degrees)
            elif operation == "flip":
                return await self._flip_element(element, flip_direction)
            elif operation == "scale":
                return await self._scale_element(element, scale_factor)
            elif operation == "duplicate":
                return await self._duplicate_element(element, offset_x, offset_y)
            elif operation == "bring_to_front":
                return await self._bring_to_front(element)
            elif operation == "send_to_back":
                return await self._send_to_back(element)
            elif operation == "move_up":
                return await self._move_up(element)
            elif operation == "move_down":
                return await self._move_down(element)
            else:
                return CanvasToolResult(
                    success=False,
                    error=f"不支持的操作: {operation}"
                )

        except Exception as e:
            logger.error(f"CanvasTransformTool exception: {e}", exc_info=True)
            return CanvasToolResult(success=False, error=f"变换操作异常: {str(e)}")

    def _build_element_full_attrs(self, element, bounds: Dict[str, float]) -> Dict[str, Any]:
        """构建完整元素属性"""
        attrs = element.to_dict()

        x = bounds["x"]
        y = bounds["y"]
        width = bounds["width"]
        height = bounds["height"]

        attrs["computed"] = {
            "center_x": x + width / 2,
            "center_y": y + height / 2,
            "right_edge_x": x + width,
            "bottom_edge_y": y + height,
            "left_edge": x,
            "right_edge": x + width,
            "top_edge": y,
            "bottom_edge": y + height,
        }

        if element.styles:
            attrs["styles_summary"] = {
                "fill": element.styles.fill,
                "stroke": element.styles.stroke,
                "stroke_width": element.styles.stroke_width,
                "opacity": element.styles.opacity,
                "rotation": element.styles.rotation,
            }

        return attrs

    def _build_spatial_hints(self, element, bounds: Dict[str, float]) -> Dict[str, Any]:
        """构建空间感知信息"""
        spatial_hints = {
            "aligned_with": [],
            "distance_to_nearest_edge": None,
        }

        if not self.canvas or not self.canvas._elements:
            return spatial_hints

        try:
            current_left = bounds["x"]
            current_right = bounds["x"] + bounds["width"]
            current_top = bounds["y"]
            current_bottom = bounds["y"] + bounds["height"]

            other_elements = []
            for elem_id, elem in self.canvas._elements.items():
                if elem_id == element.id:
                    continue
                if not elem.visible:
                    continue
                elem_bounds = elem.get_bounds()
                other_elements.append({
                    "id": elem_id,
                    "type": elem.type,
                    "bounds": elem_bounds,
                })

            if not other_elements:
                return spatial_hints

            min_distance = float("inf")
            nearest_edge_info = None
            alignment_tolerance = 5

            for other in other_elements:
                other_bounds = other["bounds"]
                other_left = other_bounds["x"]
                other_right = other_bounds["x"] + other_bounds["width"]
                other_top = other_bounds["y"]
                other_bottom = other_bounds["y"] + other_bounds["height"]
                other_id = other["id"]

                # 检测对齐关系
                if abs(current_left - other_left) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.left")
                elif abs(current_right - other_right) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.right")
                elif abs(current_left - other_right) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.right_edge")
                elif abs(current_right - other_left) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.left_edge")

                if abs(current_top - other_top) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.top")
                elif abs(current_bottom - other_bottom) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.bottom")
                elif abs(current_top - other_bottom) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.bottom_edge")
                elif abs(current_bottom - other_top) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.top_edge")

                current_center_x = current_left + bounds["width"] / 2
                other_center_x = other_left + other_bounds["width"] / 2
                if abs(current_center_x - other_center_x) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.center_x")

                current_center_y = current_top + bounds["height"] / 2
                other_center_y = other_top + other_bounds["height"] / 2
                if abs(current_center_y - other_center_y) <= alignment_tolerance:
                    spatial_hints["aligned_with"].append(f"{other_id}.center_y")

                # 计算距离
                if current_right < other_left:
                    horiz_dist = other_left - current_right
                elif current_left > other_right:
                    horiz_dist = current_left - other_right
                else:
                    horiz_dist = 0

                if current_bottom < other_top:
                    vert_dist = other_top - current_bottom
                elif current_top > other_bottom:
                    vert_dist = current_top - other_bottom
                else:
                    vert_dist = 0

                distance = horiz_dist + vert_dist

                if distance > 0 and distance < min_distance:
                    min_distance = distance
                    nearest_edge_info = {
                        "distance": min_distance,
                        "direction": self._get_distance_direction(
                            current_left, current_right, current_top, current_bottom,
                            other_left, other_right, other_top, other_bottom
                        )
                    }

            if nearest_edge_info:
                spatial_hints["distance_to_nearest_edge"] = nearest_edge_info["distance"]
                spatial_hints["nearest_edge_direction"] = nearest_edge_info["direction"]

        except Exception as e:
            logger.warning(f"[CanvasTransformTool] Failed to build spatial hints: {e}")

        return spatial_hints

    def _get_distance_direction(self,
                                cur_left: float, cur_right: float,
                                cur_top: float, cur_bottom: float,
                                oth_left: float, oth_right: float,
                                oth_top: float, oth_bottom: float) -> str:
        """计算当前元素到目标元素的距离方向"""
        directions = []

        if cur_right <= oth_left:
            directions.append("right")
        elif cur_left >= oth_right:
            directions.append("left")

        if cur_bottom <= oth_top:
            directions.append("below")
        elif cur_top >= oth_bottom:
            directions.append("above")

        return "-".join(directions) if directions else "overlapping"

    def _get_recent_elements(self) -> List[Dict[str, Any]]:
        """
        获取画布上最近的元素列表

        返回画布上的所有可见元素（最多20个），包含 element_id、bounds、position、size 等信息。
        用于让 Agent 了解当前画布上的元素布局，以便进行下一步操作。
        """
        recent_elements = []
        if not self.canvas or not self.canvas._elements:
            return recent_elements

        try:
            # 获取所有可见元素
            for elem_id, elem in self.canvas._elements.items():
                if not elem.visible:
                    continue
                bounds = elem.get_bounds()
                element_info = {
                    "element_id": elem_id,
                    "type": elem.type,
                    "bounds": bounds,
                    "position": elem.position,
                    "size": elem.size,
                }
                # 添加样式摘要
                if elem.styles:
                    element_info["styles_summary"] = {
                        "fill": elem.styles.fill,
                        "stroke": elem.styles.stroke,
                        "stroke_width": elem.styles.stroke_width,
                    }
                recent_elements.append(element_info)

                # 限制数量
                if len(recent_elements) >= 20:
                    break

        except Exception as e:
            logger.warning(f"[CanvasTransformTool] Failed to get recent elements: {e}")

        return recent_elements

    async def _rotate_element(self, element, degrees: int) -> CanvasToolResult:
        """旋转元素"""
        current_rotation = element.styles.rotation if element.styles else 0
        new_rotation = (current_rotation + degrees) % 360

        updates = {"styles": {"rotation": new_rotation}}
        success = await self.canvas.update_element(element.id, updates)

        if success:
            updated_element = self.canvas.get_element(element.id)
            bounds = updated_element.get_bounds() if updated_element else element.get_bounds()
            element_full_attrs = self._build_element_full_attrs(updated_element, bounds)
            spatial_hints = self._build_spatial_hints(updated_element, bounds)
            element_data = updated_element.to_dict() if updated_element else element.to_dict()
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "rotate",
                    "degrees": degrees,
                    "new_rotation": new_rotation,
                    "bounds": bounds,
                    "element_position": updated_element.position if updated_element else element.position,
                    "element_size": updated_element.size if updated_element else element.size,
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已将元素 {element.id} 旋转 {degrees} 度"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="旋转元素失败")

    async def _flip_element(self, element, direction: str) -> CanvasToolResult:
        """镜像翻转元素 - 真正翻转路径点"""
        from ..canvas.canvas_core import ElementMetadata

        # 获取元素的 path 点
        raw_points = element.metadata.points if element.metadata else []
        if not raw_points:
            return CanvasToolResult(
                success=False,
                error="当前元素不支持翻转操作"
            )

        # 计算中心点
        bounds = element.get_bounds()
        cx = bounds["x"] + bounds["width"] / 2
        cy = bounds["y"] + bounds["height"] / 2

        # 翻转 path 点（兼容 [{"x":x,"y":y}] 和 [[x,y]] 两种格式）
        new_points = []
        for point in raw_points:
            # 兼容两种格式
            if isinstance(point, dict):
                px, py = point["x"], point["y"]
            else:
                px, py = point[0], point[1]

            if direction == "horizontal":
                # 水平镜像：相对于中心点翻转 x 坐标
                new_px = 2 * cx - px
                new_py = py
            else:
                # 垂直镜像：相对于中心点翻转 y 坐标
                new_px = px
                new_py = 2 * cy - py
            new_points.append([new_px, new_py])

        # 计算新的边界
        xs = [p[0] for p in new_points]
        ys = [p[1] for p in new_points]
        new_x = min(xs)
        new_y = min(ys)
        new_width = max(xs) - min(xs)
        new_height = max(ys) - min(ys)

        # 更新元素
        new_metadata = ElementMetadata(
            shape_type=element.metadata.shape_type if element.metadata else "path",
            points=new_points,
            stroke_color=element.metadata.stroke_color if element.metadata else None,
            stroke_width=element.metadata.stroke_width if element.metadata else None,
            fill_color=element.metadata.fill_color if element.metadata else None,
        )

        updates = {
            "position": {"x": new_x, "y": new_y},
            "size": {"width": new_width, "height": new_height},
            "metadata": new_metadata.to_dict() if hasattr(new_metadata, 'to_dict') else new_metadata,
        }

        success = await self.canvas.update_element(element.id, updates)

        if success:
            # 获取更新后的元素以计算 spatial_hints
            updated_element = self.canvas.get_element(element.id)
            new_bounds = updated_element.get_bounds() if updated_element else bounds
            element_full_attrs = self._build_element_full_attrs(updated_element, new_bounds)
            spatial_hints = self._build_spatial_hints(updated_element, new_bounds)
            element_data = updated_element.to_dict() if updated_element else None
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "flip",
                    "direction": direction,
                    "bounds": new_bounds,
                    "element_position": {"x": new_x, "y": new_y},
                    "element_size": {"width": new_width, "height": new_height},
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已将元素 {element.id} {'水平' if direction == 'horizontal' else '垂直'}镜像翻转"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="镜像翻转元素失败")

    async def _scale_element(self, element, scale_factor: float) -> CanvasToolResult:
        """缩放元素"""
        if scale_factor <= 0:
            return CanvasToolResult(success=False, error="缩放比例必须大于0")

        bounds = element.get_bounds()
        cx = bounds["x"] + bounds["width"] / 2
        cy = bounds["y"] + bounds["height"] / 2

        new_width = bounds["width"] * scale_factor
        new_height = bounds["height"] * scale_factor

        new_x = cx - new_width / 2
        new_y = cy - new_height / 2

        new_bounds = {"x": new_x, "y": new_y, "width": new_width, "height": new_height}

        updates = {
            "position": {"x": new_x, "y": new_y},
            "size": {"width": new_width, "height": new_height}
        }

        success = await self.canvas.update_element(element.id, updates)

        if success:
            updated_element = self.canvas.get_element(element.id)
            element_full_attrs = self._build_element_full_attrs(updated_element, new_bounds)
            spatial_hints = self._build_spatial_hints(updated_element, new_bounds)
            element_data = updated_element.to_dict() if updated_element else None
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "scale",
                    "scale_factor": scale_factor,
                    "bounds": new_bounds,
                    "element_position": {"x": new_x, "y": new_y},
                    "element_size": {"width": new_width, "height": new_height},
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已将元素 {element.id} 缩放 {scale_factor} 倍"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="缩放元素失败")

    async def _duplicate_element(self, element, offset_x: float, offset_y: float) -> CanvasToolResult:
        """复制元素到新位置"""
        import uuid

        new_id = str(uuid.uuid4())
        new_position = {
            "x": element.position["x"] + offset_x,
            "y": element.position["y"] + offset_y
        }

        from ..canvas.canvas_core import CanvasElement
        new_element = CanvasElement(
            id=new_id,
            type=element.type,
            position=new_position,
            size=element.size.copy(),
            z_index=element.z_index + 1,
            metadata=element.metadata,
            styles=element.styles,
            created_by="agent"
        )

        success = await self.canvas.add_element(new_element)

        if success:
            new_bounds = new_element.get_bounds()
            element_full_attrs = self._build_element_full_attrs(new_element, new_bounds)
            spatial_hints = self._build_spatial_hints(new_element, new_bounds)
            element_data = new_element.to_dict()
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": new_id,
                    "original_element_id": element.id,
                    "operation": "duplicate",
                    "offset": {"x": offset_x, "y": offset_y},
                    "bounds": new_bounds,
                    "element_position": new_position,
                    "element_size": new_element.size,
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已复制元素 {element.id} 到新位置"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="复制元素失败")

    async def _delete_element(self, element) -> CanvasToolResult:
        """删除元素"""
        success = await self.canvas.delete_elements([element.id])

        if success:
            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "delete",
                    "message": f"已删除元素 {element.id}"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="删除元素失败")

    async def _bring_to_front(self, element) -> CanvasToolResult:
        """置顶元素"""
        max_z = 0
        for elem_id, elem in self.canvas._elements.items():
            if elem.z_index > max_z:
                max_z = elem.z_index

        new_z = max_z + 1
        updates = {"z_index": new_z}
        success = await self.canvas.update_element(element.id, updates)

        if success:
            updated_element = self.canvas.get_element(element.id)
            bounds = updated_element.get_bounds() if updated_element else element.get_bounds()
            element_full_attrs = self._build_element_full_attrs(updated_element, bounds)
            spatial_hints = self._build_spatial_hints(updated_element, bounds)
            element_data = updated_element.to_dict() if updated_element else element.to_dict()
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "bring_to_front",
                    "new_z_index": new_z,
                    "bounds": bounds,
                    "element_position": updated_element.position if updated_element else element.position,
                    "element_size": updated_element.size if updated_element else element.size,
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已将元素 {element.id} 置顶"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="置顶元素失败")

    async def _send_to_back(self, element) -> CanvasToolResult:
        """置底元素"""
        min_z = 0
        for elem_id, elem in self.canvas._elements.items():
            if elem.z_index < min_z:
                min_z = elem.z_index

        new_z = min_z - 1
        updates = {"z_index": new_z}
        success = await self.canvas.update_element(element.id, updates)

        if success:
            updated_element = self.canvas.get_element(element.id)
            bounds = updated_element.get_bounds() if updated_element else element.get_bounds()
            element_full_attrs = self._build_element_full_attrs(updated_element, bounds)
            spatial_hints = self._build_spatial_hints(updated_element, bounds)
            element_data = updated_element.to_dict() if updated_element else element.to_dict()
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "send_to_back",
                    "new_z_index": new_z,
                    "bounds": bounds,
                    "element_position": updated_element.position if updated_element else element.position,
                    "element_size": updated_element.size if updated_element else element.size,
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已将元素 {element.id} 置底"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="置底元素失败")

    async def _move_up(self, element) -> CanvasToolResult:
        """上移一层"""
        new_z = element.z_index + 1
        updates = {"z_index": new_z}
        success = await self.canvas.update_element(element.id, updates)

        if success:
            updated_element = self.canvas.get_element(element.id)
            bounds = updated_element.get_bounds() if updated_element else element.get_bounds()
            element_full_attrs = self._build_element_full_attrs(updated_element, bounds)
            spatial_hints = self._build_spatial_hints(updated_element, bounds)
            element_data = updated_element.to_dict() if updated_element else element.to_dict()
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "move_up",
                    "new_z_index": new_z,
                    "bounds": bounds,
                    "element_position": updated_element.position if updated_element else element.position,
                    "element_size": updated_element.size if updated_element else element.size,
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已将元素 {element.id} 上移一层"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="上移元素失败")

    async def _move_down(self, element) -> CanvasToolResult:
        """下移一层"""
        new_z = element.z_index - 1
        updates = {"z_index": new_z}
        success = await self.canvas.update_element(element.id, updates)

        if success:
            updated_element = self.canvas.get_element(element.id)
            bounds = updated_element.get_bounds() if updated_element else element.get_bounds()
            element_full_attrs = self._build_element_full_attrs(updated_element, bounds)
            spatial_hints = self._build_spatial_hints(updated_element, bounds)
            element_data = updated_element.to_dict() if updated_element else element.to_dict()
            recent_elements = self._get_recent_elements()

            return CanvasToolResult(
                success=True,
                content=json.dumps({
                    "element_id": element.id,
                    "operation": "move_down",
                    "new_z_index": new_z,
                    "bounds": bounds,
                    "element_position": updated_element.position if updated_element else element.position,
                    "element_size": updated_element.size if updated_element else element.size,
                    "element_data": element_data,
                    "element_full_attrs": element_full_attrs,
                    "spatial_hints": spatial_hints,
                    "recent_elements": recent_elements,
                    "message": f"已将元素 {element.id} 下移一层"
                }, ensure_ascii=False)
            )
        return CanvasToolResult(success=False, error="下移元素失败")


# 画板工具定义列表
CANVAS_TOOL_DEFINITIONS = [
    CanvasUnderstandTool,
    CanvasSuggestTool,
    CanvasGenerateTool,
    CanvasEditTool,
    CanvasOperateTool,
    CanvasGlobalEditTool,
    CanvasImageEditTool,
    CanvasDrawTool,
    CanvasUndoTool,
    CanvasSnapshotTool,
    CanvasShapeTool,
    CanvasTransformTool,
    GetCanvasToolResultTool,
]
