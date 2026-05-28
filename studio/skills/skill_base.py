"""Skill 数据模型和异常定义"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class SkillLoadError(Exception):
    """技能加载错误，包含文件路径和具体原因"""
    def __init__(self, message: str, skill_file: str = None):
        self.skill_file = skill_file
        super().__init__(message)


@dataclass
class SkillSummary:
    """技能摘要信息（用于 L1 目录披露）"""
    name: str
    description: str
    version: str = "1.0"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
        }


@dataclass
class SkillDefinition:
    """
    技能定义完整数据模型
    """
    name: str
    prompt: str  # 完整技能指令（L3）
    description: str = ""  # 简短描述（用于 L1 目录）
    version: str = "1.0"
    agent_type: str = ""  # 指定适用 Agent 类型
    catalog_instruction: Optional[str] = None  # 第二级披露概要（L2）
    allowed_tools: List[str] = field(default_factory=list)  # 允许的工具列表
    dependencies: List[str] = field(default_factory=list)  # 技能依赖（仅文档）

    @classmethod
    def from_dict(cls, data: dict) -> "SkillDefinition":
        """从字典创建 SkillDefinition"""
        return cls(
            name=data.get("name", ""),
            prompt=data.get("prompt", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            agent_type=data.get("agent_type", ""),
            catalog_instruction=data.get("catalog_instruction"),
            allowed_tools=data.get("allowed_tools", []),
            dependencies=data.get("dependencies", []),
        )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "prompt": self.prompt,
            "description": self.description,
            "version": self.version,
            "agent_type": self.agent_type,
            "catalog_instruction": self.catalog_instruction,
            "allowed_tools": self.allowed_tools,
            "dependencies": self.dependencies,
        }

    def get_summary(self) -> SkillSummary:
        """获取技能摘要"""
        return SkillSummary(
            name=self.name,
            description=self.description,
            version=self.version,
        )