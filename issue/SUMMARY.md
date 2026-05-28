# Studio 模块问题总结

## 已修复的问题

### 1. 同步阻塞问题
**文件**: `agent/models/llm_gateway.py`

**问题**: DashScope SDK 的 `Generation.call()` 和 `MultiModalConversation.call()` 是同步调用，在 async 函数中会阻塞整个事件循环，导致服务器无响应。

**解决方案**: 使用 `asyncio.get_event_loop().run_in_executor()` 将同步调用放到线程池中执行。

```python
# 修改前
response = Generation.call(**params)

# 修改后
loop = asyncio.get_event_loop()
response = await loop.run_in_executor(None, lambda: Generation.call(**params))
```

---

### 2. 多模态模型 API 选择问题
**文件**: `agent/models/llm_gateway.py`

**问题**: `qwen3.6-plus` 是多模态模型，只支持 `multimodal-generation` API，不支持 `text-generation` API。但代码在处理纯文本请求时错误地使用了 `Generation.call()`。

**解决方案**: 根据模型类型判断使用哪个 API。添加了 `MULTIMODAL_MODELS` 集合，并在 `invoke` 方法中判断：

```python
MULTIMODAL_MODELS = {"qwen3.6-plus", "qwen3.6-flash", "qwen-v1.5-plus", "qwen-v1.5-turbo"}

# 在 invoke 方法中
model = params.get("model", "")
is_multimodal_model = model.lower() in LLMRequest.MULTIMODAL_MODELS

if is_multimodal_model or req._is_multimodal():
    result = await provider.multimodal_conversation(req.messages, **params)
else:
    result = await provider.chat_completions(req.messages, **params)
```

---

### 3. 多模态 API 响应格式问题
**文件**: `agent/models/llm_gateway.py`

**问题**: `MultiModalConversation` API 返回的 `content` 格式是 `[{"text": "..."}]`（列表），而不是 `Generation` API 返回的字符串格式。

**解决方案**: 在提取 content 时处理两种格式：

```python
raw_content = result["choices"][0]["message"].get("content", "")
if isinstance(raw_content, list):
    content = "".join(item.get("text", "") for item in raw_content if isinstance(item, dict))
else:
    content = raw_content
```

---

### 4. 后端启动脚本问题
**文件**: `start_backend.py`

**问题**: 在 Windows 上使用 `subprocess.CREATE_NEW_CONSOLE` 无法正确后台运行，启动脚本会等待进程结束。

**解决方案**: 使用 `subprocess.STARTUPINFO` 和 `subprocess.SW_HIDE` 来隐藏窗口并后台运行。

---

### 5. 模块导入路径问题
**文件**: `config-ui/backend/main.py`

**问题**: `from config_service import ConfigService` 找不到模块，因为 `config_service.py` 在 `backend` 目录下，而不是 `redbook` 根目录。

**解决方案**: 在 `main.py` 中添加 `backend_dir` 到 `sys.path`：

```python
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
```

---

## 待解决/网络问题

### DashScope API 连接重置问题
**问题描述**: 连续调用 DashScope API 时出现 `ConnectionResetError (10054, '远程主机强迫关闭了一个现有的连接。')`。

**分析**:
- 第一次 API 调用成功
- 第二次 API 调用失败，连接被重置
- 错误发生在 SSL/TLS 握手阶段

**可能原因**:
1. DashScope API 的限流机制
2. 网络代理问题（如果有使用代理）
3. SDK 内部连接池管理问题

**解决方案** (2026-04-29):
使用 DashScope SDK 原生异步 API `AioGeneration` 替代同步调用：

1. **新增导入**:
   - `aiohttp`, `certifi`, `ssl`
   - `from dashscope.aio import AioGeneration`

2. **新增 `DashScopeProvider` 特性**:
   - `__init__`: 初始化 `_session` 和 `_connector`
   - `_get_session()`: 创建带 SSL 上下文的 `aiohttp.ClientSession`
   - `_close_session()`: 关闭 session

3. **`_call_with_retry` 方法**:
   - 使用原生异步 `AioGeneration.call(session=session)`
   - 自动重试连接错误
   - 连接错误时关闭并重建 session
   - 指数退避：1s, 2s, 4s

4. **`chat_completions`**: 使用 `AioGeneration.call` 原生异步
5. **`multimodal_conversation`**: 使用线程池 + `_call_with_retry_threadpool` 重试
6. **`LLMGateway.close()`**: 新增方法用于关闭所有 session

**SSL 配置**:
```python
ssl_context = ssl.create_default_context(cafile=certifi.where())
connector = aiohttp.TCPConnector(
    limit=100,           # 总连接数限制
    limit_per_host=30,   # 每主机连接数限制
    ssl=ssl_context,
)
```

**文件**: `agent/models/llm_gateway.py`

---

## 已修改的文件清单

1. `agent/models/llm_gateway.py` - 修复同步阻塞、API 选择、响应格式
2. `start_backend.py` - 修复后台启动
3. `config-ui/backend/main.py` - 修复模块导入

---

## 测试命令

```bash
# 测试健康检查
curl http://localhost:8080/api/health

# 测试创建会话
curl -X POST http://localhost:8080/api/studio/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_input":"测试需求","materials":[]}'
```
