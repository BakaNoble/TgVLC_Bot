# TgVLC_Bot 代码修复报告

生成日期：2026-04-07

---

## 一、修复概览

| 类别 | 数量 |
|------|------|
| 功能性 Bug | 8 |
| 长期运行稳定性修复 | 3 |
| 性能优化 | 4 |
| 测试用例 | 40 |
| 涉及文件 | 4 |

---

## 二、功能性缺陷修复

### BUG-1: VLC 播放器竞态条件（严重）

**文件**: `vlc_player.py:116-119`

**问题**: `_on_stop` 是 VLC 事件回调，在 VLC 内部线程中执行。当 `open_file` 调用 `self.stop()` 后立即设置 `self.current_file = file_path`，VLC 的 `_on_stop` 回调可能在此之后异步执行，将 `current_file` 重置为 `None`，导致播放状态丢失。

**修复**: 移除 `_on_stop` 回调中的 `self.current_file = None` 赋值。`current_file` 由 `stop()` 方法（主线程调用）和 `open_file` 方法管理，不应由异步回调修改。

```python
# 修复前
def _on_stop(self, event):
    self._is_playing = False
    self.current_file = None  # 危险：异步回调修改共享状态

# 修复后
def _on_stop(self, event):
    self._is_playing = False
    # current_file 由 stop() 和 open_file 在主调用线程中管理
```

---

### BUG-2: VLC 媒体对象内存泄漏（中等）

**文件**: `vlc_player.py:231,643,657`

**问题**: 通过 `vlc.Instance.media_new()` 创建的媒体对象在调用 `player.set_media()` 后从未调用 `release()`。VLC 使用引用计数管理媒体对象，未释放的媒体对象会持续占用内存，长时间运行后可能导致内存溢出。

**修复**: 在所有 `set_media()` 调用后添加 `media.release()`。涉及 3 处：`open_file`、`_handle_playback_end`（顺序播放自动下一集）、`_handle_playback_end`（单集循环）。

```python
# 修复后
media = self.instance.media_new(file_path)
self.player.set_media(media)
media.release()  # 释放媒体对象引用，避免内存泄漏
```

---

### BUG-3: 设置菜单状态返回错误（中等）

**文件**: `main.py:616-717`

**问题**: `manage_directories`、`manage_users`、`add_current_user` 三个回调处理器没有显式返回 `STATE_SETTINGS_MENU`，导致落入默认的 `return STATE_SELECTING_ACTION`。这会导致 ConversationHandler 处于错误的状态，可能引起后续操作异常。

**修复**: 为这三个处理器添加正确的 `return STATE_SETTINGS_MENU`。

---

### BUG-4: `edit_message_text` 内容不变时崩溃（中等）

**文件**: `main.py` 多处

**问题**: Telegram API 在消息内容未变化时抛出 `BadRequest: Message is not modified`。在快速重复操作（如连续点击播放/暂停、音量调节）时，状态文本可能相同，导致未捕获异常。

**修复**:
1. 添加 `_safe_edit_message` 辅助函数，捕获 `BadRequest: not modified` 异常
2. 改进 `error_handler` 静默处理此类异常

---

### BUG-5: 配置 DEFAULT_CONFIG 浅拷贝导致共享状态（低）

**文件**: `config.py:177`

**问题**: `_create_default_config` 使用 `self.DEFAULT_CONFIG.copy()` 进行浅拷贝。`DEFAULT_CONFIG` 包含嵌套字典（如 `telegram`、`proxy` 等），浅拷贝只复制外层引用，多个 Config 实例会共享同一嵌套字典对象。

**修复**: 使用 `copy.deepcopy(self.DEFAULT_CONFIG)` 确保完全独立的配置副本。

---

### BUG-6: 双重 save_config 调用（低）

**文件**: `main.py:689-690`

**问题**: `config.add_allowed_user(user_id)` 内部已调用 `save_config()`，外部又调用了一次 `config.save_config()`，导致配置文件被写入两次。

**修复**: 移除外部的 `config.save_config()` 调用。

---

### BUG-7: 目录添加状态管理缺失（低）

**文件**: `main.py:519-525`

**问题**: 进入 `STATE_ADDING_DIRECTORY` 状态时，未设置 `context.user_data['current_state']`。文本输入处理器依赖此值判断当前状态，导致目录路径输入只能靠后备的盘符匹配逻辑处理，代码脆弱。

**修复**:
1. 进入添加目录状态时设置 `context.user_data['current_state'] = STATE_ADDING_DIRECTORY`
2. 在 `handle_text_input` 中添加明确的 `STATE_ADDING_DIRECTORY` 处理分支
3. 改进盘符检测逻辑，支持所有 Windows 盘符而非硬编码 C/D/E/F

---

### BUG-8: 跳转步长输入缺少上限验证（低）

**文件**: `main.py:750-761`

**问题**: 音量步长有 1-100 的范围校验，但跳转步长只检查 `> 0`，用户可输入任意大的值（如 9999），与 `config._validate_int` 的上限 300 不一致。

**修复**: 统一跳转步长输入验证范围为 1-300，与配置加载时的验证一致。

---

## 三、性能优化

### PERF-1: 日志压缩检查频率优化

**文件**: `logger.py:87-95`

**问题**: 原实现在每次日志写入后都调用 `_check_and_compact()`，该方法会打开文件逐行计数。高频日志场景下，I/O 开销显著。

**修复**: 引入写入计数器 `_write_count`，每 100 次写入才触发一次压缩检查。

### PERF-2: 日志压缩内存效率优化

**文件**: `logger.py:121-140`

**问题**: 注释声称"使用双指针方式避免全量加载到内存"，但实际实现将所有行加载到 Python 列表中（`all_lines = []`），对于 10000+ 行日志文件会占用大量内存。

**修复**: 使用 `collections.deque(maxlen=10000)` 作为滑动窗口，流式读取文件，内存中始终只保留最新的 10000 行。

### PERF-3: 日志压缩预检查优化

**文件**: `logger.py:99-118`

**问题**: 原压缩检查每次都打开文件逐行计数。

**修复**: 先通过文件大小估算行数（假设平均每行 200 字节），仅在估算超过阈值时才精确计数，避免不必要的文件 I/O。

### PERF-4: 文件清理 glob 模式修正

**文件**: `logger.py:331,370,589`

**问题**: 使用 `*.log*` glob 模式匹配范围过广，可能误匹配非日志文件。

**修复**: 改用精确的 `.log` 后缀匹配。

---

## 四、改进项

### IMPROVE-1: 上下集按钮显示逻辑

**文件**: `main.py:203-206`

**原问题**: `_get_show_episode_buttons` 仅依赖 `file_browser` 当前目录状态。如果用户在 A 目录播放视频后浏览到 B 目录，上/下集按钮会错误地基于 B 目录的视频数量。

**修复**: 优先检查 `vlc_player.video_list`（实际播放上下文），仅在无播放列表时回退到 `file_browser` 状态。

### IMPROVE-2: clear_logs 资源安全清理

**文件**: `logger.py:586-596`

**问题**: Windows 下 RotatingFileHandler 持有文件锁，直接删除文件会抛出 PermissionError。

**修复**: 清理前先关闭所有文件 handler，并添加 PermissionError 异常处理。

---

## 五、测试覆盖

新增测试文件 `tests/test_core.py`，包含 40 个测试用例：

| 测试类 | 测试数 | 覆盖范围 |
|--------|--------|----------|
| TestConfig | 11 | 默认配置、深拷贝、加载/保存、权限、目录管理、验证 |
| TestFileBrowser | 7 | 目录浏览、分页、视频文件操作、导航、大小格式化 |
| TestVLCPlayer | 9 | 时间格式化、播放模式、状态查询、音量范围、跳转范围、线程安全、VLC健康检查、状态原子操作 |
| TestLogger | 11 | 日志记录、分页查询、过滤、搜索、统计、归档、压缩、导出、清理 |
| TestTextUtils | 2 | Windows 盘符检测 |

全部测试通过。

---

## 六、长期运行稳定性修复（针对"1-2天无响应"问题）

### STAB-1: 线程安全保护（关键）

**文件**: `vlc_player.py` 全文

**问题**: `_is_playing`、`current_file` 等状态变量被多个线程并发访问：
- VLC 事件回调（VLC 内部线程）
- `_playback_monitor_loop`（监控守护线程）
- `button_callback`（asyncio 主线程）

原代码对共享状态没有同步保护，可能导致：
- `get_status()` 读取到半更新状态，返回错误信息
- `open_file` 设置 `current_file` 后被 `_on_stop` 异步覆盖为 None
- 监控线程和事件回调同时触发 `_handle_playback_end` 导致重复处理

**修复**: 引入 `_state_lock`（`threading.Lock`），所有对 `_is_playing`、`current_file` 的读写都在锁保护下进行：
```python
with self._state_lock:
    self.current_file = file_path
    self._is_playing = True

# get_status 中
with self._state_lock:
    current_file = self.current_file  # 拷贝到局部变量再使用
```

### STAB-2: 监控线程 VLC API 超时保护（关键）

**文件**: `vlc_player.py:_safe_vlc_call`, `_playback_monitor_loop`

**问题**: `_playback_monitor_loop` 每秒调用 `player.get_time()` / `player.get_length()`。这些是 libvlc C 函数的 Python 绑定，调用时会持有 GIL 并阻塞。如果 VLC 进程崩溃或卡死：
- API 调用可能无限期阻塞，导致监控线程永久挂起
- 连续的异常会不断抛出但无法恢复

**修复**:
1. 新增 `_safe_vlc_call()` 方法：通过辅助线程 + `join(timeout)` 实现 API 调用超时保护
2. 监控线程使用带超时的 API 调用，3 秒内未返回则视为 VLC 无响应
3. 连续 5 次 API 调用失败时触发自动恢复

### STAB-3: VLC 健康检查与自动恢复机制（关键）

**文件**: `vlc_player.py:_check_vlc_health`, `_try_recover_vlc`

**问题**: VLC 进程崩溃后，整个机器人无法控制播放器，所有操作返回失败。没有检测和恢复机制，只能手动重启。

**修复**: 新增 `_check_vlc_health()` 和 `_try_recover_vlc()` 方法：
1. `_consecutive_errors` 计数器跟踪连续 API 调用失败次数
2. 超过阈值（默认 5 次）时自动触发恢复
3. `_try_recover_vlc()` 保存当前播放状态（文件、视频列表、播放模式），释放旧 VLC 资源，等待 2 秒后重新初始化 VLC，并尝试恢复之前的播放
4. 恢复成功后重置错误计数器

```python
def _try_recover_vlc(self):
    saved_file = self.current_file          # 保存播放状态
    saved_video_list = self.video_list.copy()
    # ... 释放旧资源 ...
    if self.initialize():                    # 重新初始化
        self.video_list = saved_video_list   # 恢复状态
        self.open_file(saved_file, ...)      # 尝试恢复播放
```

---

## 七、文件修改清单

| 文件 | 修改类型 |
|------|----------|
| `vlc_player.py` | Bug 修复 + 线程安全 + VLC 健康检查/自动恢复 |
| `main.py` | Bug 修复（状态返回、验证、容错） |
| `config.py` | Bug 修复（深拷贝） |
| `logger.py` | 性能优化 + Bug 修复 |
| `tests/test_core.py` | 新增（40 个测试用例） |
