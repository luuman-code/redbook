"""
Iterator - 迭代控制器

参考 plan.md:
- 用户修改流程：
  1. 修改意图识别（改标题、改第3张图、加重卖点语气…）
  2. 定位修改范围：只修改受影响的组件，保留其他部分
  3. 版本管理：基于上一版增量修改，所有历史版本保留，支持回退
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..config.studio_config import StudioConfig
from ..models.brief import Brief
from ..models.content_item import ContentItem, ContentType, ItemStatus
from ..models.content_plan import ContentPlan
from ..models.session import Session
from ..models.version import Version
from ..debug_logger import get_logger, get_workflow_logger

# 获取日志记录器
logger = get_logger("iterator")

# 导入 agent 模块的请求类
from agent.models.llm_gateway import LLMRequest

if TYPE_CHECKING:
    from .critic import UserFeedback


@dataclass
class IterationResult:
    """迭代结果"""
    success: bool
    modified_items: List[ContentItem]  # 本次修改的内容项
    new_version: Optional[Version] = None
    error: Optional[str] = None
    iteration_count: int = 0


class Iterator:
    """
    迭代控制器

    职责：
    1. 管理迭代次数
    2. 确定修改范围（只修改受影响的部分）
    3. 创建版本快照
    4. 支持版本回退
    """

    def __init__(self, llm_gateway=None, config: StudioConfig = None):
        """
        初始化 Iterator

        Args:
            llm_gateway: LLM 网关实例
            config: Studio 配置
        """
        self.llm_gateway = llm_gateway
        self.config = config or StudioConfig()

    async def iterate(
        self,
        session: Session,
        feedback: "UserFeedback",
        memory_context: str = "",
    ) -> IterationResult:
        """
        执行迭代修改

        Args:
            session: 当前会话
            feedback: 用户反馈
            memory_context: 记忆上下文（可选）

        Returns:
            IterationResult: 迭代结果
        """
        wf_logger = get_workflow_logger("iterator.iterate")
        wf_logger.start("iterate")
        logger.info(f"Iterate called for session: {session.session_id}, feedback: {feedback.user_input[:50]}...")

        try:
            # 检查迭代次数
            current_iteration = len(session.versions)
            logger.debug(f"Current iteration: {current_iteration}, max: {self.config.max_iterations}")

            if current_iteration >= self.config.max_iterations:
                logger.warning(f"Max iterations reached: {self.config.max_iterations}")
                wf_logger.end("iterate", success=False, message="max_iterations")
                return IterationResult(
                    success=False,
                    modified_items=[],
                    error=f"已达到最大迭代次数 ({self.config.max_iterations})",
                    iteration_count=current_iteration,
                )

            # 解析修改范围
            logger.debug("Resolving modification targets...")
            wf_logger.start("_resolve_targets")
            target_items = self._resolve_targets(session, feedback)
            wf_logger.end("_resolve_targets", success=True, message=f"targets={len(target_items)}")
            logger.debug(f"Target items identified: {len(target_items)}")

            # 创建版本快照
            new_version_number = session.current_version + 1
            version_snapshot = Version.create_snapshot(
                session_id=session.session_id,
                version_number=new_version_number,
                plan=session.current_plan,
                items=session.items,
                change_summary=feedback.user_input,
                created_by="iterator",
            )

            # 执行修改（传入记忆上下文）
            logger.debug("Applying modifications...")
            wf_logger.start("_apply_modifications")
            modified_items = await self._apply_modifications(
                session, target_items, feedback, memory_context
            )
            wf_logger.end("_apply_modifications", success=True, message=f"modified={len(modified_items)}")
            logger.debug(f"Modified items: {len(modified_items)}")

            # 同步更新 session.current_plan.text_sections
            if modified_items and session.current_plan and session.current_plan.text_sections:
                section_map = {s.section_id: s for s in session.current_plan.text_sections}
                for item in modified_items:
                    if item.item_id in section_map:
                        section_map[item.item_id].content = item.content
                        logger.debug(f"Synced text_section {item.item_id} with modified content")

            # 更新会话
            session.current_version = new_version_number
            session.versions.append(version_snapshot)
            session.touch()

            logger.info(f"Iterate completed: version={new_version_number}, modified={len(modified_items)}")
            wf_logger.end("iterate", success=True, message=f"version={new_version_number}, modified={len(modified_items)}")

            return IterationResult(
                success=True,
                modified_items=modified_items,
                new_version=version_snapshot,
                iteration_count=new_version_number,
            )

        except Exception as e:
            logger.error(f"iterate exception: {e}", exc_info=True)
            wf_logger.error("iterate", e)
            return IterationResult(
                success=False,
                modified_items=[],
                error=f"迭代异常: {str(e)}",
                iteration_count=len(session.versions),
            )

    def _resolve_targets(
        self,
        session: Session,
        feedback: "UserFeedback",
    ) -> List[ContentItem]:
        """
        解析修改目标

        Args:
            session: 当前会话
            feedback: 用户反馈

        Returns:
            需要修改的内容项列表
        """
        intent = feedback.parsed_intent
        intent_type = intent.get("type", "general")
        target_ids = feedback.target_item_ids or []

        # 如果有明确的 target_item_ids，直接返回
        if target_ids:
            items = [session.get_item(tid) for tid in target_ids]
            return [item for item in items if item is not None]

        # 根据意图类型推断目标
        targets = []

        if intent_type == "modify_title":
            # 标题修改
            targets.extend(session.get_items_by_type(ContentType.TITLE))
            targets.extend(session.get_items_by_type(ContentType.HEADLINE))

        elif intent_type == "modify_text":
            # 正文修改
            targets.extend(session.get_items_by_type(ContentType.TEXT))

        elif intent_type == "modify_image":
            # 图片修改
            targets.extend(session.get_items_by_type(ContentType.IMAGE))

        elif intent_type == "modify_all":
            # 全部修改
            targets = session.items.copy()

        else:
            # general: 根据关键词匹配
            request = intent.get("request", "")
            targets = self._match_by_keywords(session.items, request)

        return targets

    def _match_by_keywords(
        self,
        items: List[ContentItem],
        request: str,
    ) -> List[ContentItem]:
        """根据关键词匹配内容项"""
        matched = []

        request_lower = request.lower()

        for item in items:
            # 检查内容是否包含关键词
            if request_lower in item.content.lower():
                matched.append(item)
                continue

            # 检查 item_id 是否匹配
            for keyword in ["标题", "第一段", "第三张图"]:
                if keyword in request and keyword in item.item_id:
                    matched.append(item)

        # 如果没有匹配，返回空列表（让 LLM 决定修改什么）
        return matched

    async def _apply_modifications(
        self,
        session: Session,
        target_items: List[ContentItem],
        feedback: "UserFeedback",
        memory_context: str = "",
    ) -> List[ContentItem]:
        """
        应用修改

        Args:
            session: 当前会话
            target_items: 目标内容项
            feedback: 用户反馈
            memory_context: 记忆上下文（可选）

        Returns:
            修改后的内容项列表
        """
        if not target_items:
            # 没有明确目标，让 LLM 决定修改什么
            return await self._modify_by_llm(session, feedback, memory_context)

        modified_items = []

        for item in target_items:
            modified = await self._modify_item(session, item, feedback, memory_context)
            if modified:
                modified_items.append(modified)

        return modified_items

    async def _modify_by_llm(
        self,
        session: Session,
        feedback: "UserFeedback",
        memory_context: str = "",
    ) -> List[ContentItem]:
        """使用 LLM 确定修改项并执行"""
        if not self.llm_gateway:
            return []

        # 构建上下文
        items_context = "\n".join([
            f"[{item.item_id}] [{item.item_type.value}]: {item.content[:100]}..."
            for item in session.items if item.content
        ])

        # 构建 prompt
        prompt = f"""根据用户反馈，确定要修改的内容项，并生成修改后的内容。

用户反馈：{feedback.user_input}

当前内容项：
{items_context}
"""

        # 如果有记忆上下文，添加到 prompt 中
        if memory_context:
            prompt += f"\n\n## 历史记忆上下文\n{memory_context}\n"

        prompt += """
请以 JSON 格式输出：
{
    "modifications": [
        {
            "item_id": "要修改的item_id",
            "new_content": "修改后的内容"
        }
    ]
}

只输出 JSON。
"""

        try:
            llm_request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000,
            )
            response = await self.llm_gateway.invoke(llm_request)

            if response.success:
                import json
                import re

                content = response.data.get("content", "")
                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    data = json.loads(json_match.group())
                    modifications = data.get("modifications", [])

                    modified_items = []
                    for mod in modifications:
                        item = session.get_item(mod.get("item_id"))
                        if item:
                            item.content = mod.get("new_content", item.content)
                            item.add_revision(
                                revised_by="iterator",
                                change_summary=feedback.user_input,
                                new_content=item.content,
                            )
                            modified_items.append(item)

                    return modified_items

        except Exception:
            pass

        return []

    async def _modify_item(
        self,
        session: Session,
        item: ContentItem,
        feedback: "UserFeedback",
        memory_context: str = "",
    ) -> Optional[ContentItem]:
        """修改单个内容项"""
        if not self.llm_gateway:
            return None

        # 构建 prompt
        prompt = f"""请根据用户反馈修改以下内容。

原始内容：
{item.content}

用户反馈：{feedback.user_input}
"""

        # 如果有记忆上下文，添加到 prompt 中
        if memory_context:
            prompt += f"\n\n## 历史记忆上下文\n{memory_context}\n"

        prompt += "\n请生成修改后的内容，只输出修改后的内容文本，不要有其他说明。"

        try:
            llm_request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            response = await self.llm_gateway.invoke(llm_request)

            if response.success:
                import re
                raw_content = response.data.get("content", "")
                # 去除思考内容（移除 <think>...</think> 块和 "Here's a thinking:" 格式）
                import re
                if 'Final Text:' in raw_content:
                    parts = raw_content.split('Final Text:', 1)
                    if len(parts) > 1:
                        new_content = parts[1].strip()
                        # 去除末尾的 *(Matches...) 等元信息
                        new_content = re.sub(r'\s*\*\(.*?\)\*$', '', new_content, flags=re.DOTALL)
                        new_content = re.sub(r'\s*\(Matches.*', '', new_content, flags=re.DOTALL)
                        new_content = re.sub(r'\s*Output matches.*', '', new_content, flags=re.DOTALL)
                        new_content = re.sub(r'\s*\[Done\.\]\s*$', '', new_content, flags=re.DOTALL)
                        new_content = re.sub(r'\s*✅\s*$', '', new_content, flags=re.DOTALL)
                        new_content = new_content.strip()
                    else:
                        new_content = raw_content.strip()
                else:
                    new_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL)
                    new_content = re.sub(r'Here\'s a thinking:.*?(?=\n\n|\Z)', '', new_content, flags=re.DOTALL)
                    new_content = re.sub(r'\[Output Generation\].*', '', new_content)
                    new_content = re.sub(r'\(Output Generation\).*', '', new_content)
                    new_content = re.sub(r'\(Self-Correction[^)]*\).*', '', new_content)
                    new_content = re.sub(r'\(Note:.*?\)(?=\n|$)', '', new_content)
                    new_content = new_content.strip()

                # 记录修改
                item.add_revision(
                    revised_by="iterator",
                    change_summary=feedback.user_input,
                    new_content=new_content,
                )

                item.content = new_content
                item.status = ItemStatus.COMPLETED

                return item

        except Exception:
            pass

        return None

    def rollback(self, session: Session, target_version: int) -> bool:
        """
        回退到指定版本

        Args:
            session: 当前会话
            target_version: 目标版本号

        Returns:
            是否成功
        """
        for version in session.versions:
            if version.version_number == target_version:
                # 恢复 plan
                from ..models.content_plan import ContentPlan
                session.current_plan = ContentPlan.from_dict(version.plan_snapshot)

                # 恢复 items
                from ..models.content_item import ContentItem
                session.items = [
                    ContentItem.from_dict(item_data)
                    for item_data in version.items_snapshot
                ]

                session.current_version = target_version
                session.touch()
                return True

        return False

    def get_version_history(self, session: Session) -> List[Dict[str, Any]]:
        """获取版本历史"""
        return [
            {
                "version_number": v.version_number,
                "created_at": v.created_at.isoformat(),
                "created_by": v.created_by,
                "change_summary": v.change_summary,
            }
            for v in session.versions
        ]

    async def compose_version(
        self,
        session: Session,
        version_selections: Dict[str, int],
    ) -> IterationResult:
        """
        从不同版本中选择性组合成新版本

        Args:
            session: 当前会话
            version_selections: 版本选择字典，格式为 {"item_type": version_number}
                               例如: {"title": 2, "text_1": 1, "image_1": 3}

        Returns:
            IterationResult: 迭代结果
        """
        logger.info(f"compose_version called for session: {session.session_id}")
        logger.debug(f"version_selections: {version_selections}")

        try:
            # 检查版本选择是否有效
            if not version_selections:
                return IterationResult(
                    success=False,
                    modified_items=[],
                    error="版本选择为空",
                    iteration_count=session.current_version,
                )

            # 解析版本选择，建立 item_id 到版本号的映射
            # version_selections 格式: {"title": 2, "text_0": 1, "image_1": 3}
            item_version_map: Dict[str, int] = {}
            for key, version_num in version_selections.items():
                # key 可能是 "title" 或 "text_0" 这样的格式
                item_version_map[key] = version_num

            # 创建版本快照前的 items 副本
            current_items_copy = session.items.copy()

            # 收集从各版本提取的 items
            composed_items: List[ContentItem] = []
            change_summaries: List[str] = []

            # 处理版本选择
            for item_identifier, target_version in version_selections.items():
                # 查找目标版本
                version_data = None
                for v in session.versions:
                    if v.version_number == target_version:
                        version_data = v
                        break

                if not version_data:
                    logger.warning(f"Version {target_version} not found, skipping {item_identifier}")
                    continue

                # 从版本快照中提取对应的 item
                found_item = None
                for item_data in version_data.items_snapshot:
                    item_id = item_data.get("item_id", "")
                    item_type = item_data.get("item_type", "")

                    # 匹配逻辑：支持精确匹配和类型匹配
                    # item_identifier 可能是 "title", "text_0", "image_1" 等
                    matches_exact = item_id == item_identifier
                    matches_type_index = False

                    # 解析 item_identifier 和 item_id 的类型和索引
                    identifier_parts = item_identifier.split("_")
                    item_id_parts = item_id.split("_")

                    if len(identifier_parts) >= 1 and len(item_id_parts) >= 1:
                        # 检查类型是否匹配
                        id_type = identifier_parts[0]
                        target_type = item_id_parts[0]

                        # 类型别名映射
                        type_aliases = {
                            "text": ["text", "paragraph", "content"],
                            "title": ["title", "headline"],
                            "image": ["image", "img", "picture"],
                        }

                        is_type_match = False
                        for canonical, aliases in type_aliases.items():
                            if id_type in aliases or target_type in aliases:
                                if id_type in aliases and target_type in aliases:
                                    is_type_match = True
                                elif id_type == canonical or target_type == canonical:
                                    is_type_match = True

                        if is_type_match:
                            # 有索引的情况
                            if len(identifier_parts) >= 2 and len(item_id_parts) >= 2:
                                try:
                                    idx1 = int(identifier_parts[1])
                                    idx2 = int(item_id_parts[1])
                                    matches_type_index = (idx1 == idx2)
                                except ValueError:
                                    pass
                            else:
                                # 无索引时检查类型是否一致
                                matches_type_index = (id_type == target_type)

                    if matches_exact or matches_type_index:
                        found_item = item_data
                        break

                if found_item:
                    # 从快照数据创建 ContentItem
                    from ..models.content_item import ContentItem
                    composed_item = ContentItem.from_dict(found_item)
                    composed_items.append(composed_item)
                    change_summaries.append(f"从 V{target_version} 的 {item_identifier} 提取")
                else:
                    logger.warning(f"Item {item_identifier} not found in V{target_version}")

            if not composed_items:
                return IterationResult(
                    success=False,
                    modified_items=[],
                    error="未找到任何指定的内容项",
                    iteration_count=session.current_version,
                )

            # 更新 session.items
            session.items = composed_items

            # 创建新版本快照
            new_version_number = session.current_version + 1
            version_snapshot = Version.create_snapshot(
                session_id=session.session_id,
                version_number=new_version_number,
                plan=session.current_plan,
                items=session.items,
                change_summary=f"从多个版本组合: {change_summaries}",
                created_by="iterator",
            )

            # 更新会话
            session.current_version = new_version_number
            session.versions.append(version_snapshot)
            session.touch()

            logger.info(f"compose_version completed: version={new_version_number}, composed={len(composed_items)}")

            return IterationResult(
                success=True,
                modified_items=composed_items,
                new_version=version_snapshot,
                iteration_count=new_version_number,
            )

        except Exception as e:
            logger.error(f"compose_version exception: {e}", exc_info=True)
            return IterationResult(
                success=False,
                modified_items=[],
                error=f"组合版本异常: {str(e)}",
                iteration_count=session.current_version,
            )
