"""Configuration API routes"""

import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from config_service import ConfigService
from models.model_config import ModelType, ModelProviderConfig, ModelConfig

router = APIRouter()


# Pydantic request/response models
class ModelConfigUpdate(BaseModel):
    """模型配置更新请求"""
    primary: Optional[ModelProviderConfig] = None
    fallback: Optional[ModelProviderConfig] = None


class EnvironmentActivate(BaseModel):
    """环境激活请求"""
    pass


class ConfigImport(BaseModel):
    """配置导入请求"""
    config: Dict[str, Any]


def get_config_service() -> ConfigService:
    """获取配置服务实例"""
    return ConfigService()


@router.get("")
async def get_config():
    """获取完整配置"""
    service = get_config_service()
    return service.get_config()


@router.get("/models")
async def get_all_models():
    """获取所有模型配置"""
    service = get_config_service()
    config = service.get_config()
    active_env = service.get_active_environment()
    environments = config.get('environments', {})
    env_config = environments.get(active_env, {})
    return {
        "activeEnvironment": active_env,
        "models": env_config.get('models', {})
    }


@router.get("/models/{model_type}")
async def get_model(model_type: str):
    """获取指定模型配置"""
    service = get_config_service()

    # 验证模型类型
    try:
        ModelType(model_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的模型类型: {model_type}")

    model_config = service.get_model_config(model_type)
    if model_config is None:
        raise HTTPException(status_code=404, detail=f"模型 {model_type} 不存在")

    return model_config


@router.put("/models/{model_type}")
async def update_model(model_type: str, config: ModelConfigUpdate):
    """更新模型配置"""
    service = get_config_service()

    # 验证模型类型
    try:
        ModelType(model_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的模型类型: {model_type}")

    config_dict = config.model_dump()

    # For video sub-models (video_t2v, video_i2v, etc.), the config is stored directly without primary/fallback wrapper
    # Extract the actual config based on what's provided
    if config.primary is not None:
        # Regular model with primary/fallback structure
        final_config = {
            "primary": config.primary.model_dump() if hasattr(config.primary, 'model_dump') else config.primary,
        }
        if config.fallback is not None:
            final_config["fallback"] = config.fallback.model_dump() if hasattr(config.fallback, 'model_dump') else config.fallback
    else:
        # Video sub-model - config is stored directly (flattened)
        final_config = config_dict

    success = service.update_model_config(model_type, final_config)

    if not success:
        raise HTTPException(status_code=500, detail="更新模型配置失败")

    return {"message": "更新成功", "model": model_type}


@router.post("/models/{model_type}/test")
async def test_model_connection(model_type: str):
    """测试模型连接"""
    service = get_config_service()

    # 验证模型类型
    try:
        ModelType(model_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的模型类型: {model_type}")

    model_config = service.get_model_config(model_type)
    if model_config is None:
        raise HTTPException(status_code=404, detail=f"模型 {model_type} 不存在")

    primary = model_config.get('primary', {})
    api_url = primary.get('api_url', '')
    api_key = primary.get('api_key', '')

    # 简单的连接测试
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            test_url = f"{api_url.rstrip('/')}/models"

            response = await client.get(test_url, headers=headers)
            if response.status_code == 200:
                return {"status": "ok", "message": "连接成功"}
            else:
                return {"status": "error", "message": f"连接失败: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"连接失败: {str(e)}"}


@router.get("/environments")
async def get_environments():
    """获取环境列表"""
    service = get_config_service()
    config = service.get_config()
    environments = config.get('environments', {})
    active_env = service.get_active_environment()

    result = []
    for env_name, env_config in environments.items():
        result.append({
            "name": env_name,
            "description": env_config.get('$comment', '').strip(),
            "is_active": env_name == active_env
        })

    return result


@router.post("/environments/{env}/activate")
async def activate_environment(env: str):
    """激活指定环境"""
    service = get_config_service()
    success = service.set_active_environment(env)

    if not success:
        raise HTTPException(status_code=404, detail=f"环境不存在: {env}")

    return {"message": "环境激活成功", "activeEnvironment": env}


@router.post("/export")
async def export_config():
    """导出配置"""
    service = get_config_service()
    config = service.export_config()
    return config


@router.post("/import")
async def import_config(config: Dict[str, Any]):
    """导入配置"""
    service = get_config_service()
    success = service.import_config(config)

    if not success:
        raise HTTPException(status_code=500, detail="导入配置失败")

    return {"message": "导入成功"}
