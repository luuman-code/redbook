"""通用 SkillRegistry 类 - 可被所有 Agent 复用"""

import threading
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from .skill_base import SkillDefinition, SkillLoadError, SkillSummary


class SkillRegistry:
    """
    技能注册表 - 通用类，可被所有 Agent 复用

    设计原则：
    1. 线程安全 - 所有对 self.skills 的访问都在 self._lock 保护下
    2. 对话历史驱动 - 通过检查对话历史判断技能是否已激活，无需单独的状态管理
    3. 动态注册 - register() 只影响新的激活请求，不影响已在会话中激活的技能
    4. Fail-Fast - 初始化时全量校验，有问题立刻报错
    """

    def __init__(self, skill_dir: str):
        """
        初始化 SkillRegistry

        Args:
            skill_dir: 技能文件目录路径
        """
        self.skill_dir = Path(skill_dir)
        self.skills: Dict[str, dict] = {}
        self._lock = threading.Lock()

        # 初始化时加载所有技能
        self._load_all_skills()

    def _load_all_skills(self) -> None:
        """初始化时全量加载所有技能文件"""
        if not self.skill_dir.exists():
            # 目录不存在，创建空目录
            self.skill_dir.mkdir(parents=True, exist_ok=True)
            return

        # 检查是否有 _registry.yaml 作为入口
        registry_file = self.skill_dir / "_registry.yaml"
        if registry_file.exists():
            self._load_from_registry(registry_file)
        else:
            # 无 registry 时，自动扫描 *.yaml（排除 _registry.yaml）
            self._load_from_glob()

        # 全量校验所有技能
        self._validate_all_skills()

    def _load_from_registry(self, registry_file: Path) -> None:
        """从 _registry.yaml 加载技能"""
        with open(registry_file, 'r', encoding='utf-8') as f:
            registry = yaml.safe_load(f)

        for skill_info in registry.get('skills', []):
            skill_file = self.skill_dir / skill_info['file']
            if not skill_file.exists():
                raise SkillLoadError(
                    f"Registry references missing file: {skill_file}",
                    skill_file=str(registry_file)
                )
            self._load_skill_file(skill_file)

    def _load_from_glob(self) -> None:
        """自动扫描 *.yaml 文件"""
        for f in self.skill_dir.glob("*.yaml"):
            if f.stem == "_registry":
                continue
            self._load_skill_file(f)

    def _load_skill_file(self, skill_file: Path) -> None:
        """加载单个技能文件"""
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                skill_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SkillLoadError(
                f"Skill file '{skill_file.name}' has invalid YAML format: {e}",
                skill_file=str(skill_file)
            )

        if not skill_data:
            raise SkillLoadError(
                f"Skill file '{skill_file.name}' is empty",
                skill_file=str(skill_file)
            )

        # 校验必填字段
        if 'name' not in skill_data:
            raise SkillLoadError(
                f"Skill file '{skill_file.name}' missing required field: name",
                skill_file=str(skill_file)
            )
        if 'prompt' not in skill_data:
            raise SkillLoadError(
                f"Skill file '{skill_file.name}' missing required field: prompt",
                skill_file=str(skill_file)
            )

        skill_name = skill_data['name']

        with self._lock:
            # 检测重复名称
            if skill_name in self.skills:
                raise SkillLoadError(
                    f"Duplicate skill name '{skill_name}' found in '{skill_file.name}'",
                    skill_file=str(skill_file)
                )
            self.skills[skill_name] = skill_data

    def _validate_all_skills(self) -> None:
        """全量校验所有技能"""
        names = [s.get('name') for s in self.skills.values()]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            raise SkillLoadError(f"Duplicate skill names found: {duplicates}")

    def get_skill_prompt(self, name: str) -> Optional[str]:
        """获取技能完整 prompt"""
        with self._lock:
            return self.skills.get(name, {}).get('prompt')

    def get_skill_catalog_instruction(self, name: str) -> Optional[str]:
        """获取技能 catalog_instruction（第二级披露）"""
        with self._lock:
            return self.skills.get(name, {}).get('catalog_instruction')

    def get_allowed_tools(self, name: str) -> List[str]:
        """获取技能允许的工具列表"""
        with self._lock:
            return self.skills.get(name, {}).get('allowed_tools', [])

    def get_all_summaries(self) -> List[SkillSummary]:
        """获取所有技能的摘要列表"""
        with self._lock:
            summaries = []
            for skill_data in self.skills.values():
                summaries.append(SkillSummary(
                    name=skill_data.get('name', ''),
                    description=skill_data.get('description', ''),
                    version=skill_data.get('version', '1.0'),
                ))
            return summaries

    def get_skill_definition(self, name: str) -> Optional[SkillDefinition]:
        """获取完整技能定义"""
        with self._lock:
            skill_data = self.skills.get(name)
            if not skill_data:
                return None
            return SkillDefinition.from_dict(skill_data)

    def register(self, skill_data: dict) -> None:
        """
        动态注册新技能（线程安全）

        注意：动态注册只影响新的激活请求，不影响已在会话中激活的技能。
        """
        if 'name' not in skill_data:
            raise SkillLoadError("Cannot register skill without name")
        if 'prompt' not in skill_data:
            raise SkillLoadError("Cannot register skill without prompt")

        with self._lock:
            self.skills[skill_data['name']] = skill_data

    def reload(self) -> None:
        """重新加载所有技能（线程安全）"""
        with self._lock:
            self.skills.clear()

        self._load_all_skills()