# TgVLC_Bot 内部实现文档

本文档描述 TgVLC_Bot 项目的内部实现细节，包括架构决策、线程安全机制和设计模式。

---

## 1. 线程安全模型

### 1.1 VLC Player 线程安全

VLC 事件回调运行在 VLC 的内部 C 线程，不受 Python GIL 保护。以下是线程安全措施：

**锁层次结构（按获取顺序）**：
```
1. _recovery_lock_for_recovery (threading.Lock)
2. _state_lock (threading.Lock)
3. _end_handling_lock (threading.Lock)
```

**事件回调处理**：
```python
# _on_media_end 设置标志，监控线程处理实际逻辑
def _on_media_end(self, event):
    with self._state_lock:
        self._playback_end_pending = True
        self._is_playing = False
```

**监控线程轮询**：
- 检查 `_playback_end_pending` 标志
- 使用 `_end_handling_lock` 防止重复处理
- 调用 `_handle_playback_end()` 处理播放结束

**恢复机制**：
- `_try_recover_vlc()` 使用 `_recovery_lock_for_recovery` 防止并发恢复
- 超时获取锁（1秒），避免死锁

### 1.2 FileBrowser 线程安全

全局 `file_browser` 实例在多用户并发访问时存在竞态条件。

**解决方案**：使用 `SessionManager` 为每个用户维护独立的 `UserSession`。

```python
class SessionManager:
    def get_session(self, user_id: int) -> UserSession:
        """线程安全的会话获取"""
        if user_id not in self._sessions:
            with self._sessions_lock:
                self._sessions[user_id] = UserSession(user_id)
        return self._sessions[user_id]
```

### 1.3 Logger 线程安全

- 所有公共方法使用 `_lock` 保护
- Logger 创建使用有界缓存（最多 20 个）
- LRU 追踪确保最久未使用的 logger 被移除

---

## 2. 状态机设计

### 2.1 ConversationHandler 状态

| 状态 | 值 | 描述 |
|------|-----|------|
| STATE_SELECTING_ACTION | 0 | 主菜单状态 |
| STATE_BROWSING_FILES | 1 | 浏览文件状态 |
| STATE_SELECTING_FILE | 2 | 选择文件状态 |
| STATE_SETTINGS_MENU | 3 | 设置菜单状态 |
| STATE_ADDING_DIRECTORY | 4 | 添加目录状态（等待输入） |
| STATE_WAITING_VOLUME_STEP | 5 | 等待音量步长输入 |
| STATE_WAITING_SEEK_STEP | 6 | 等待跳转步长输入 |

### 2.2 CallbackRouter 路由机制

重构后使用 `CallbackRouter` 分散处理逻辑：

```python
class CallbackRouter:
    def __init__(self):
        self._handlers = []

    async def route(self, update, context) -> int:
        data = update.callback_query.data
        for handler in self._handlers:
            if handler.handles(data):
                return await handler.handle(update, context)
        return STATE_SELECTING_ACTION
```

**注册的 Handler**：
- `NavigationHandler` - 主菜单导航
- `PlaybackHandler` - 播放控制
- `FileBrowseHandler` - 文件浏览
- `SettingsHandler` - 设置管理
- `SubtitleHandler` - 字幕管理

---

## 3. VLC 事件回调线程模型

VLC 事件（`MediaPlayerEndReached`, `MediaPlayerPlaying`, 等）运行在 VLC 的内部线程。

**设计决策**：
- 回调只设置标志，不执行复杂逻辑
- 复杂逻辑委托给监控线程
- 使用 `_playback_end_pending` 标志协调

**监控线程职责**：
- 定期检查播放状态
- 检测播放卡顿
- 处理播放结束事件
- VLC 进程存活检测

---

## 4. 配置验证

### 4.1 类型强制转换

| 配置项 | 期望类型 | 转换方式 |
|--------|----------|----------|
| `allowed_user_ids` | List[int] | `_parse_user_ids()` 尝试 `int()` 转换 |
| `admin_user_ids` | List[int] | `_parse_user_ids()` 尝试 `int()` 转换 |
| `proxy_port` | int | `_validate_int()` 限制在 1-65535 |
| `video_directories` | List[str] | 确保是列表，非列表转为空列表 |

### 4.2 validate() 检查项

```python
def validate(self) -> List[str]:
    errors = []
    # Telegram Token 非空
    # VLC 路径是有效文件
    # 视频目录存在
    # volume_step 在 1-100 范围
    # seek_step 在 1-300 范围
    # 代理配置（启用时）：
    #   - type 是 'socks5' 或 'http'
    #   - host 非空
    #   - port 在 1-65535 范围
    return errors
```

---

## 5. 日志系统

### 5.1 日志文件结构

```
logs/
├── bot.log          # RotatingFileHandler (10MB, 5备份)
├── bot_logs.json    # 当前 JSON 日志（行格式）
└── archive/         # 每日归档
    └── logs_YYYYMMDD.json
```

### 5.2 JSON 日志格式

```json
{
  "timestamp": "2026-04-11T10:30:00.123456",
  "level": "INFO",
  "module": "main",
  "message": "User 88029460 started bot",
  "user_id": 88029460,
  "chat_id": 123456789,
  "details": null
}
```

### 5.3 自动清理策略

- **时间**：保留 30 天
- **大小**：最大 500MB
- **行数**：超过 10000 行时压缩，保留最新 10000 条

---

## 6. 崩溃恢复机制

### 6.1 恢复触发条件

1. **API 调用超时**：`consecutive_errors >= 5`
2. **VLC 进程死亡**：`is_running()` 返回 False

### 6.2 恢复流程

```
1. 检查 _recovery_lock_for_recovery（防止并发）
2. 检查 _recovery_attempts >= 3（最大尝试次数）
3. 保存当前状态（file, video_list, index, mode）
4. 停止监控线程
5. 释放 VLC 资源
6. 等待 2 秒
7. 重新初始化 VLC
8. 恢复状态
9. 如果有保存的文件，尝试恢复播放
```

### 6.3 恢复状态管理

```python
# 成功时重置计数器
if self.initialize():
    self._recovery_attempts = 0

# 失败时不重置，让下次继续尝试
# 直到达到最大次数后放弃
```

---

## 7. 代码组织

### 7.1 模块结构

```
handlers/           # Telegram 回调处理
├── __init__.py
├── base.py         # CallbackHandler 基类
├── callbacks.py    # 回调前缀和解析
├── keyboards.py    # 键盘构建器
├── navigation.py   # 导航处理
├── playback.py     # 播放控制
├── settings.py     # 设置管理
├── file_browse.py  # 文件浏览
└── subtitle.py     # 字幕管理

session.py          # 每用户会话管理
```

### 7.2 主要类

| 类 | 职责 |
|----|------|
| `VLCPlayer` | VLC 播放器控制、播放状态管理 |
| `FileBrowser` | 文件系统浏览、分页 |
| `Config` | 配置加载、保存、验证 |
| `AdvancedLogger` | JSON 日志、归档、轮转 |
| `SessionManager` | 每用户会话隔离 |
| `UserSession` | 单用户会话状态 |

---

## 8. PyInstaller 打包注意事项

### 8.1 Frozen 模式检测

```python
def get_app_dir() -> str:
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式：使用 exe 所在目录
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
```

### 8.2 日志目录

打包后日志写入 exe 同目录下的 `logs/` 文件夹，而非 `_internal/` 子目录。

### 8.3 配置文件

打包后从 exe 同目录读取 `config.yaml`，而非 `_internal/` 子目录。

---

## 9. 设计模式

### 9.1 单例模式

全局实例在模块级别创建：
```python
# config.py
config = Config()

# vlc_player.py
vlc_player = VLCPlayer()

# file_browser.py
file_browser = FileBrowser()
```

### 9.2 模板方法模式

`CallbackHandler` 基类定义处理模板：
```python
async def handle(self, update, context) -> int:
    # 公共前置检查
    if not await self.check_permission(update):
        return ConversationHandler.END
    # 调用子类具体实现
    return await self._handle(update, context)
```

### 9.3 策略模式

不同的 Handler 实现不同的回调处理策略：
- `NavigationHandler` 处理导航
- `PlaybackHandler` 处理播放控制
- ...

---

## 10. 错误处理

### 10.1 Telegram 错误处理

- `BadRequest "not modified"`：忽略（快速重复操作导致）
- 网络错误：python-telegram-bot 内部自动重试

### 10.2 VLC 错误处理

- API 调用超时：标记错误，触发健康检查
- VLC 进程死亡：触发恢复机制
- 播放卡顿：10 秒无进度视为卡顿

### 10.3 文件系统错误处理

- `PermissionError`：跳过无权限的文件/目录
- `OSError`：记录警告，继续处理其他项

---

## 11. 性能优化

### 11.1 FileBrowser

- 分页加载：避免大目录一次性加载
- 目录优先排序：提升导航体验
- 延迟初始化：Session 按需创建
- `get_next_video()` / `get_previous_video()`：单次遍历 `self.items`（原为双重遍历）
- `get_video_file_index()`：直接迭代 `self.items`，不再构建中间列表
- 依赖注入：`FileBrowser` 接受 `app_config` 参数，避免全局耦合

### 11.2 Logger

- 有界缓存：避免 logger 无限增长（最多 20 个，LRU 淘汰）
- 批量检查：每 100 次写入才检查压缩
- 流式处理：压缩时使用 deque 滑动窗口

### 11.3 VLC API

- 超时保护：防止 VLC 卡死导致主线程阻塞
- 辅助线程：API 调用在独立线程执行
- `get_status()` 批量查询：4 个 VLC API 调用合并为 1 个线程（减少 75% 线程创建）
- `set_subtitle_track()` 内嵌轨道验证：直接调用 VLC API，跳过文件系统扫描
- `_find_vlc_window()` 窗口句柄缓存：首次查找后缓存，后续通过 `IsWindow()` 快速验证
- 自适应监控轮询：播放中 1s / 空闲 5s，可中断睡眠机制

### 11.4 Handlers

- `_handle_file()` 索引查找：复用已构建的 `video_list` 做 `list.index()`，避免重复遍历

### 11.5 Watchdog

- 指数退避重启：避免网络波动时频繁重启（60s → 1800s 上限）
- 恢复检测：网络恢复后自动重置退避计数器
