"""
Mode Router - ML + LLM 混合路由模式切换

使用 ML + LLM 混合路由来判断用户意图并切换 Agent 模式：
1. ML 模型（Sentence-Embeddings + Logistic Regression）做意图分类
2. 本地 LLM (Ollama) 做最终验证
3. 混合路由：ML 高置信度直接返回，低置信度 LLM 验证

使用方法:
    from studio.canvas.mode_router import ModeRouter, get_mode_router
    router = get_mode_router()
    result = await router.route("请帮我画一个史蒂夫")
"""

import asyncio
import os
import pickle
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import numpy as np

# 设置 HuggingFace 离线模式（使用本地缓存）
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# ==================== 配置 ====================
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:1.5b-instruct-q4_K_M"

# 置信度阈值
HIGH_CONFIDENCE_THRESHOLD = 0.85
LOW_CONFIDENCE_THRESHOLD = 0.5

# 模型路径
MODEL_DIR = Path("C:/Users/LWB/Desktop/redbook/data/ml_models")
MODEL_FILE = MODEL_DIR / "mode_router_classifier.pkl"

# Embedding 模型本地缓存路径 (与 LLMRAG 相同)
LOCAL_EMBEDDING_PATH = "C:/Users/LWB/.cache/BAAI/bge-large-zh-v1___5"


# ==================== 数据模型 ====================
class Mode(Enum):
    DAILY = "daily"
    PLANNING = "planning"


@dataclass
class RouteResult:
    """路由结果"""
    mode: Mode
    confidence: float
    method: str  # "ml_high", "ml_llm_verify", "llm_fallback"
    reason: str


# ==================== 训练数据 ====================
TRAINING_DATA = [
    # === DAILY 模式样本 ===
    ("你好啊，今天怎么样？", "daily"),
    ("早上好！", "daily"),
    ("晚安，明天见", "daily"),
    ("今天天气真不错", "daily"),
    ("我想聊聊天", "daily"),
    ("谢谢你帮我", "daily"),
    ("这个想法很有趣", "daily"),
    ("再见啦", "daily"),
    ("你好啊", "daily"),
    ("您好", "daily"),
    ("谢谢你的帮助", "daily"),
    ("不好意思打扰了", "daily"),
    ("没关系", "daily"),
    ("没事没事", "daily"),
    ("下次再见", "daily"),
    ("拜拜", "daily"),

    # === PLANNING 模式样本 ===
    ("请帮我画一个史蒂夫", "planning"),
    ("帮我设计一个logo", "planning"),
    ("能否制作一个宣传海报", "planning"),
    ("我想画一幅画", "planning"),
    ("帮我创建一个图标", "planning"),
    ("请根据这张图片绘制一个类似的", "planning"),
    ("在指定区域绘制一个图形", "planning"),
    ("我想做一个表情包", "planning"),
    ("帮我生成一张图片", "planning"),
    ("把红色改成蓝色", "planning"),
    ("重新调整一下尺寸", "planning"),
    ("在这个基础上添加一些装饰", "planning"),
    ("帮我画个圆", "planning"),
    ("绘制一个矩形", "planning"),
    ("创建一个五角星", "planning"),
]


# ==================== ML 分类器 ====================
class MLModeClassifier:
    """基于 Sentence-Embeddings + Logistic Regression 的 ML 分类器"""

    def __init__(self):
        self.classifier = None
        self.scaler = None
        self.label_encoder: Dict[str, int] = {}
        self.label_decoder: Dict[int, str] = {}
        self.embedding_model = None
        self.tfidf_vectorizer = None  # TF-IDF 向量化器（备用）
        self.is_trained = False

        # 确保模型目录存在
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        # 尝试加载预训练模型
        self._try_load_model()

    def _get_embedding_model(self):
        """获取 embedding 模型 - 使用本地缓存的 BAAI/bge-large-zh-v1.5"""
        if self.embedding_model is None:
            from sentence_transformers import SentenceTransformer
            # 优先使用本地缓存
            if Path(LOCAL_EMBEDDING_PATH).exists():
                self.embedding_model = SentenceTransformer(LOCAL_EMBEDDING_PATH)
            else:
                # 回退到直接使用模型名称
                self.embedding_model = SentenceTransformer("BAAI/bge-large-zh-v1.5")
        return self.embedding_model

    def _get_classifier(self):
        """获取分类器"""
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        if self.classifier is None:
            self.classifier = {
                'model': LogisticRegression(
                    max_iter=1000,
                    solver='lbfgs',
                    C=1.0,
                    class_weight='balanced',
                    random_state=42
                ),
                'scaler': StandardScaler()
            }
        return self.classifier

    def _try_load_model(self) -> bool:
        """尝试加载预训练模型"""
        if not MODEL_FILE.exists():
            return False

        try:
            with open(MODEL_FILE, 'rb') as f:
                data = pickle.load(f)

            self.classifier = data.get('classifier')
            self.label_encoder = data.get('label_encoder', {})
            self.label_decoder = data.get('label_decoder', {})
            self.scaler = data.get('scaler')
            self.is_trained = data.get('is_trained', False)
            return True
        except Exception:
            return False

    def _save_model(self) -> None:
        """保存模型到磁盘"""
        data = {
            'classifier': self.classifier,
            'label_encoder': self.label_encoder,
            'label_decoder': self.label_decoder,
            'scaler': self.classifier.get('scaler') if self.classifier else None,
            'is_trained': self.is_trained,
        }

        with open(MODEL_FILE, 'wb') as f:
            pickle.dump(data, f)

    def _extract_features(self, query: str) -> np.ndarray:
        """提取特征：Embedding + 关键词"""
        features = []

        # 1. Embedding 特征
        try:
            embedding_model = self._get_embedding_model()
            embedding = embedding_model.encode([query])[0]
            features.extend(embedding)
        except Exception as e:
            # 回退到 TF-IDF
            if self.tfidf_vectorizer is None:
                from sklearn.feature_extraction.text import TfidfVectorizer
                queries = [q for q, _ in TRAINING_DATA]
                self.tfidf_vectorizer = TfidfVectorizer(max_features=100, ngram_range=(1, 2))
                self.tfidf_vectorizer.fit(queries + [query])
            tfidf_features = self.tfidf_vectorizer.transform([query]).toarray()[0]
            features.extend(tfidf_features)

        # 2. 关键词特征
        keyword_features = self._extract_keyword_features(query)
        features.extend(keyword_features)

        return np.array(features, dtype=np.float32)

    def _extract_keyword_features(self, query: str) -> List[float]:
        """提取关键词特征"""
        features = []

        # Planning 关键词
        planning_kws = ["画", "绘制", "设计", "制作", "创建", "生成",
                        "帮我", "请帮我", "修改", "调整", "添加", "增加",
                        "生成", "绘制", "画一个", "做个"]
        features.append(sum(1 for kw in planning_kws if kw in query))

        # Daily 关键词
        daily_kws = ["你好", "您好", "早上好", "晚上好", "晚安",
                     "谢谢", "感谢", "再见", "拜拜", "天气", "聊天",
                     "好呀", "好的", "不错", "有意思"]
        features.append(sum(1 for kw in daily_kws if kw in query))

        # 消息长度
        features.append(len(query) / 100.0)

        return features

    def train(self, training_data: List[Tuple[str, str]] = None) -> Dict:
        """训练模型"""
        from sklearn.metrics import accuracy_score, precision_recall_fscore_support

        if training_data is None:
            training_data = TRAINING_DATA

        queries = [q for q, _ in training_data]
        labels = [l for _, l in training_data]

        # 编码标签
        unique_labels = sorted(set(labels))
        self.label_encoder = {label: idx for idx, label in enumerate(unique_labels)}
        self.label_decoder = {idx: label for label, idx in self.label_encoder.items()}

        # 提取特征
        X = np.array([self._extract_features(q) for q in queries])
        y = np.array([self.label_encoder[l] for l in labels])

        # 标准化
        clf = self._get_classifier()
        X_scaled = clf['scaler'].fit_transform(X)

        # 训练
        clf['model'].fit(X_scaled, y)
        y_pred = clf['model'].predict(X_scaled)

        # 计算指标
        accuracy = accuracy_score(y, y_pred)
        precision, recall, f1, _ = precision_recall_fscore_support(
            y, y_pred, average='weighted', zero_division=0
        )

        self.is_trained = True
        self._save_model()

        return {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'train_size': len(training_data)
        }

    def predict(self, query: str) -> Tuple[str, float]:
        """预测查询的类别和置信度"""
        if not self.is_trained:
            # 如果没训练，返回默认
            return "daily", 0.5

        clf = self._get_classifier()
        features = self._extract_features(query).reshape(1, -1)
        features_scaled = clf['scaler'].transform(features)

        # 预测
        pred_idx = clf['model'].predict(features_scaled)[0]
        pred_label = self.label_decoder.get(pred_idx, "daily")

        # 置信度
        probas = clf['model'].predict_proba(features_scaled)[0]
        confidence = float(max(probas))

        return pred_label, confidence


# ==================== LLM 路由 ====================
class LLMRouter:
    """基于本地 LLM (Ollama) 的路由"""

    ROUTING_PROMPT = """你是一个意图分类器，判断用户消息应该使用哪种模式。

规则：
- 闲聊、问候、日常交流、轻松对话 → daily
- 有明确任务需求、创作请求、绘图需求、规划需求 → planning

用户消息：{message}

请只返回 JSON 格式，不要有其他内容：
{{"mode": "daily 或 planning", "confidence": 0.0到1.0之间的数字, "reason": "简短原因"}}
"""

    def __init__(self, ollama_url: str = OLLAMA_URL, model: str = OLLAMA_MODEL):
        self.ollama_url = ollama_url
        self.model = model

    async def route(self, message: str) -> RouteResult:
        """使用 LLM 判断意图"""
        import aiohttp

        prompt = self.ROUTING_PROMPT.format(message=message)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 100,
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        llm_output = result.get("response", "")

                        try:
                            json_str = self._extract_json(llm_output)
                            data = json.loads(json_str)

                            mode = Mode.PLANNING if data.get("mode") == "planning" else Mode.DAILY
                            confidence = float(data.get("confidence", 0.5))
                            reason = data.get("reason", "")

                            return RouteResult(
                                mode=mode,
                                confidence=confidence,
                                method="llm",
                                reason=reason
                            )
                        except json.JSONDecodeError:
                            return RouteResult(
                                mode=Mode.DAILY,
                                confidence=0.3,
                                method="llm",
                                reason=f"JSON解析失败: {llm_output[:50]}..."
                            )
                    else:
                        error_text = await response.text()
                        return RouteResult(
                            mode=Mode.DAILY,
                            confidence=0.3,
                            method="llm",
                            reason=f"LLM 请求失败: {response.status}"
                        )

        except Exception as e:
            return RouteResult(
                mode=Mode.DAILY,
                confidence=0.3,
                method="llm",
                reason=f"LLM 调用异常: {str(e)[:50]}"
            )

    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        import re
        match = re.search(r'\{[^{}]*\}', text)
        if match:
            return match.group()
        return text.strip()


# ==================== ML + LLM 混合路由 ====================
class ModeRouter:
    """ML + LLM 混合路由"""

    def __init__(self):
        self.ml_classifier = MLModeClassifier()
        self.llm_router = LLMRouter()

        # 训练 ML 模型
        print("[ModeRouter] 正在训练 ML 模型...")
        metrics = self.ml_classifier.train()
        print(f"[ModeRouter] ML 模型训练完成: 准确率={metrics['accuracy']*100:.1f}%")

    async def route(self, message: str) -> RouteResult:
        """混合路由：ML 高置信度直接返回，低置信度 LLM 验证"""

        # 1. ML 模型预测
        ml_pred, ml_confidence = self.ml_classifier.predict(message)
        ml_mode = Mode.PLANNING if ml_pred == "planning" else Mode.DAILY

        # 2. 根据置信度决定
        if ml_confidence >= HIGH_CONFIDENCE_THRESHOLD:
            # 高置信度，直接使用 ML 结果
            return RouteResult(
                mode=ml_mode,
                confidence=ml_confidence,
                method="ml_high",
                reason=f"ML 高置信度: {ml_confidence:.2f}"
            )

        elif ml_confidence >= LOW_CONFIDENCE_THRESHOLD:
            # 中等置信度，用 LLM 验证
            llm_result = await self.llm_router.route(message)

            if llm_result.confidence > ml_confidence:
                # LLM 更置信
                return RouteResult(
                    mode=llm_result.mode,
                    confidence=llm_result.confidence,
                    method="ml_llm_verify",
                    reason=f"ML({ml_confidence:.2f})→LLM({llm_result.confidence:.2f}) {llm_result.reason}"
                )
            else:
                # ML 更置信
                return RouteResult(
                    mode=ml_mode,
                    confidence=ml_confidence,
                    method="ml_confirm",
                    reason=f"ML({ml_confidence:.2f}) 确认"
                )

        else:
            # 低置信度，用 LLM 判断
            llm_result = await self.llm_router.route(message)
            return RouteResult(
                mode=llm_result.mode,
                confidence=llm_result.confidence,
                method="llm_fallback",
                reason=f"ML低置信度({ml_confidence:.2f})→{llm_result.reason}"
            )

    def route_sync(self, message: str) -> RouteResult:
        """同步路由（返回默认）"""
        # 同步模式下使用 ML 分类器的默认行为
        ml_pred, ml_confidence = self.ml_classifier.predict(message)
        ml_mode = Mode.PLANNING if ml_pred == "planning" else Mode.DAILY

        if ml_confidence >= HIGH_CONFIDENCE_THRESHOLD:
            return RouteResult(
                mode=ml_mode,
                confidence=ml_confidence,
                method="ml_high",
                reason=f"ML 高置信度: {ml_confidence:.2f}"
            )
        else:
            # 中低置信度返回 ML 结果，但标记需要异步验证
            return RouteResult(
                mode=ml_mode,
                confidence=ml_confidence,
                method="ml_async_verify",
                reason=f"ML({ml_confidence:.2f}) 需要异步 LLM 验证"
            )


# ==================== 单例模式 ====================
_router_instance: Optional[ModeRouter] = None


def get_mode_router() -> ModeRouter:
    """获取 ModeRouter 单例"""
    global _router_instance
    if _router_instance is None:
        _router_instance = ModeRouter()
    return _router_instance


def reset_mode_router() -> None:
    """重置 ModeRouter 单例（用于测试）"""
    global _router_instance
    _router_instance = None


# ==================== 模块导出 ====================
__all__ = [
    "ModeRouter",
    "RouteResult",
    "Mode",
    "get_mode_router",
    "reset_mode_router",
]
