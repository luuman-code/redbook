"""
ConfigService - 配置服务

单例配置服务，统一管理配置的读取和保存
"""

import json
import os
import re
import fnmatch
from typing import Dict, Any, Optional, Callable, List


class ConfigService:
    """单例配置服务"""
    _instance = None

    def __new__(cls, config_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str = None):
        if self._initialized:
            return

        self._config_path = config_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "config.json"
        )
        self._listeners: Dict[str, List[Callable]] = {}
        self._config: Dict[str, Any] = {}
        self._initialized = True
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """加载配置，支持 ${ENV_VAR} 环境变量替换"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 执行环境变量替换
                    content = self._substitute_env_vars(content)
                    self._config = json.loads(content)
                    return self._config
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                return self.get_default_config()
        return self.get_default_config()

    def _substitute_env_vars(self, content: str) -> str:
        """替换 ${ENV_VAR} 形式的環境變量"""
        pattern = r'\$\{([^}]+)\}'

        def replacer(match):
            env_var = match.group(1)
            return os.environ.get(env_var, match.group(0))

        return re.sub(pattern, replacer, content)

    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "$schema": "./schema.json",
            "$comment": "======================================== Redbook 统一配置文件 ========================================",
            "$version": "1.0.0",
            "activeEnvironment": "development",
            "environments": {
                "development": {
                    "$comment": "---------------------------------------- 【开发环境】----------------------------------------",
                    "models": {
                        "llm": {
                            "primary": {
                                "provider": "openai",
                                "api_url": "https://api.openai.com/v1",
                                "model_name": "gpt-4o",
                                "api_key": "",
                                "default_params": {
                                    "temperature": 0.7,
                                    "max_tokens": 4096,
                                    "top_p": 1.0
                                },
                                "timeout": 120,
                                "retry_count": 3,
                                "enabled": True
                            },
                            "fallback": None
                        }
                    }
                }
            }
        }

    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """保存配置，保留 $comment_* 元数据字段"""
        try:
            if config is None:
                config = self._config

            # 确保目录存在
            config_dir = os.path.dirname(self._config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)

            # 验证并合并配置
            validated_config = self._validate_and_merge_config(config)

            # 保存配置到文件
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(validated_config, f, indent=2, ensure_ascii=False)

            # 更新内部配置
            self._config = validated_config

            # 通知监听器
            self._emit('configChanged', validated_config)

            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False

    def _validate_and_merge_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证并合并配置，确保配置结构完整
        保留所有 $comment_* 元数据注释字段
        """
        if not new_config or not isinstance(new_config, dict) or len(new_config) == 0:
            print('收到空或无效配置，保持当前配置不变')
            return {**self._config}

        # 提取所有 $comment_* 元数据注释字段
        comment_fields = {
            key: value
            for key, value in new_config.items()
            if key.startswith('$comment_')
        }

        # 提取顶级元数据字段
        metadata_fields = {}
        for key in ['$schema', '$comment', '$version']:
            if key in new_config:
                metadata_fields[key] = new_config[key]

        merged_config = {
            # 保留 schema 和 version
            **metadata_fields,
            # 保留所有 $comment_* 元数据注释
            **comment_fields,
        }

        # 合并 environments 配置
        if 'environments' in new_config and new_config['environments']:
            merged_config['environments'] = {
                **self._config.get('environments', {}),
                **new_config['environments']
            }
        else:
            merged_config['environments'] = self._config.get('environments', {})

        # 合并 activeEnvironment
        merged_config['activeEnvironment'] = new_config.get(
            'activeEnvironment',
            self._config.get('activeEnvironment', 'development')
        )

        return merged_config

    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return {**self._config}

    def get_config_raw(self) -> Dict[str, Any]:
        """获取原始配置（包含未替换的环境变量）"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return self._config

    def get_model_config(self, model_type: str) -> Optional[Dict[str, Any]]:
        """获取指定模型配置"""
        active_env = self.get_active_environment()
        environments = self._config.get('environments', {})
        env_config = environments.get(active_env, {})
        models = env_config.get('models', {})
        return models.get(model_type)

    def update_model_config(self, model_type: str, config: Dict[str, Any]) -> bool:
        """更新指定模型配置"""
        active_env = self.get_active_environment()
        environments = self._config.get('environments', {})

        if active_env not in environments:
            return False

        if 'models' not in environments[active_env]:
            environments[active_env]['models'] = {}

        environments[active_env]['models'][model_type] = config
        return self.save_config()

    def get_active_environment(self) -> str:
        """获取当前活跃环境"""
        return self._config.get('activeEnvironment', 'development')

    def set_active_environment(self, env: str) -> bool:
        """切换活跃环境"""
        environments = self._config.get('environments', {})
        if env not in environments:
            return False

        self._config['activeEnvironment'] = env
        return self.save_config()

    def get_environments(self) -> List[str]:
        """获取所有环境列表"""
        return list(self._config.get('environments', {}).keys())

    def get_environment_config(self, env: str) -> Optional[Dict[str, Any]]:
        """获取指定环境配置"""
        return self._config.get('environments', {}).get(env)

    def on(self, event: str, listener: Callable) -> None:
        """添加事件监听器"""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(listener)

    def off(self, event: str, listener: Callable) -> None:
        """移除事件监听器"""
        if event in self._listeners:
            self._listeners[event] = [
                l for l in self._listeners[event] if l != listener
            ]

    def _emit(self, event: str, data: Any) -> None:
        """发出事件"""
        if event in self._listeners:
            for listener in self._listeners[event]:
                try:
                    listener(data)
                except Exception as e:
                    print(f"事件监听器执行失败: {e}")

    def export_config(self) -> Dict[str, Any]:
        """导出配置（包含元数据，用于下载）"""
        return self.get_config_raw()

    def import_config(self, config: Dict[str, Any]) -> bool:
        """导入配置（合并 $comment_* 字段）"""
        return self.save_config(config)


def get_api_key(provider: str) -> str:
    """Get API Key from environment variable"""
    env_var_map = {
        "dashscope": "DASHSCOPE_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "minimax": "MINIMAX_API_KEY",
    }
    env_var = env_var_map.get(provider.lower())
    if not env_var:
        return None
    return os.getenv(env_var)
