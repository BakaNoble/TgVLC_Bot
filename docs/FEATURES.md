# 新功能说明

## 功能一：字幕选择功能

### 功能描述
用户可以在播放视频时自由选择字幕轨道，支持内嵌字幕和外部字幕文件。系统会自动选择第一个字幕轨道，并提供便捷的字幕切换菜单。

### 功能特性

#### 1. **自动选择内嵌字幕**
- 打开视频文件时自动选择第一个字幕轨道
- 无需手动选择，立即显示字幕
- 如果视频没有字幕，则不会应用任何字幕

#### 2. **字幕选择菜单**
- 在播放控制界面添加了"📝 字幕选择"按钮
- 点击后显示所有可用的字幕轨道列表
- 显示当前选中的字幕轨道
- 未检测到字幕时显示友好提示

#### 3. **实时状态显示**
- 播放状态信息中显示当前字幕状态
- 格式：`📝 字幕: <字幕名称>` 或 `📝 字幕: 无字幕`
- 方便用户了解当前字幕情况

#### 4. **无缝切换体验**
- 选择字幕后立即应用
- 自动返回播放控制界面
- 显示切换成功的提示信息
- 不中断播放控制流程

### 使用方法

#### 打开字幕选择菜单
1. 在播放控制菜单中点击"📝 字幕选择"
2. 系统会显示字幕选择界面
3. 显示当前字幕状态和所有可用字幕列表

#### 切换字幕
1. 在字幕选择菜单中点击想要的字幕
2. 系统会立即应用所选字幕
3. 自动返回播放控制界面
4. 状态栏显示新的字幕信息

#### 返回播放控制
1. 点击"◀️ 返回播放控制"按钮
2. 系统会返回到播放控制界面
3. 保持当前播放状态不变

### 界面示例

#### 字幕选择菜单（有多字幕）
```
📝 字幕选择

📌 当前字幕：中文 (简)

📊 共检测到 3 个字幕轨道：

选择要切换的字幕：

📝 [1] English [SDH]
📝 [2] 中文 (简)
📝 [3] 中文 (繁)

[◀️ 返回播放控制]
```

#### 字幕选择菜单（无字幕）
```
📝 字幕选择

⚠️ 未检测到字幕轨道

提示：
• 确保视频文件包含内嵌字幕
• 或在同一目录下放置相同文件名的字幕文件（如 .srt, .ass）

[◀️ 返回播放控制]
```

#### 播放状态显示
```
📺 正在播放: 电影.mkv
📊 状态: 播放中
🔊 音量: 50%
⏱️ 进度: 00:15:30 / 02:30:00 (10.3%)
🖥️ 显示: 窗口
📝 字幕: 中文 (简)
```

### 技术实现

#### VLC播放器模块 (vlc_player.py)

**新增方法：**

```python
def get_subtitle_tracks(self) -> List[Tuple[int, str]]:
    """获取所有可用的字幕轨道列表"""
    # 获取VLC中的字幕轨道描述
    sub_tracks = self.player.video_get_spu_description()
    # 处理字节编码并返回列表
    ...

def set_subtitle_track(self, track_id: int) -> Tuple[bool, str]:
    """设置字幕轨道"""
    self.player.video_set_spu(track_id)
    ...

def get_current_subtitle_track(self) -> Tuple[int, str]:
    """获取当前选中的字幕轨道"""
    current_track_id = self.player.video_get_spu()
    ...

def has_multiple_subtitles(self) -> bool:
    """检查是否有多个字幕轨道可用"""
    tracks = self.get_subtitle_tracks()
    return len(tracks) > 1
```

**自动选择字幕：**
```python
def open_file(self, file_path: str, ...):
    # 打开视频后自动选择第一个字幕
    if self.player.play() == -1:
        return False, "播放失败"

    time.sleep(0.5)
    self._select_first_subtitle()  # 自动选择字幕
    ...
```

#### 主程序模块 (main.py)

**字幕选择菜单：**
```python
def get_subtitle_selection_keyboard():
    """获取字幕选择菜单键盘"""
    keyboard = []
    sub_tracks = vlc_player.get_subtitle_tracks()

    for track_id, track_name in sub_tracks:
        keyboard.append([
            InlineKeyboardButton(f"📝 {track_name}",
                               callback_data=f"select_sub_{track_id}")
        ])

    keyboard.append([InlineKeyboardButton("◀️ 返回播放控制",
                                        callback_data="back_to_playback")])
    return InlineKeyboardMarkup(keyboard)
```

**播放控制界面增强：**
```python
def get_playback_control_keyboard(show_episode_buttons: bool = False):
    keyboard = []
    # ... 其他按钮 ...
    keyboard.append([InlineKeyboardButton("📝 字幕选择",
                                       callback_data="subtitle_menu")])
    keyboard.append([InlineKeyboardButton("⏹️ 停止并返回列表",
                                       callback_data="stop_to_list")])
    return InlineKeyboardMarkup(keyboard)
```

### 支持的字幕格式

#### 内嵌字幕
- **MP4**: 通常包含SRT/UTF-8内嵌字幕
- **MKV**: 支持多种内嵌字幕（ASS/SSA/SRT/UTF-8）
- **AVI**: 可能有内嵌字幕

#### 外部字幕文件
字幕文件需与视频文件同名，放置在同一目录下：
- **SRT**: SubRip Text（最通用）
- **ASS/SSA**: Advanced SubStation Alpha
- **SUB**: MicroDVD格式
- **SBV**: YouTube格式

### 常见问题

#### Q: 为什么打开视频后没有显示字幕？
**A:** 系统会自动选择第一个字幕轨道。如果视频没有内嵌字幕或同目录下没有字幕文件，则不会显示字幕。

#### Q: 如何切换到其他字幕？
**A:** 点击"📝 字幕选择"按钮，在菜单中选择想要的字幕轨道即可。

#### Q: 字幕选择后会自动保存吗？
**A:** 当前版本不会保存字幕选择。下次播放同一视频时，仍会从第一个字幕轨道开始。

#### Q: 支持哪些语言的字幕？
**A:** 支持所有VLC支持的字幕格式和语言，包括中文、英文、日文、韩文等。

#### Q: 可以关闭字幕吗？
**A:** 当前版本需要选择一个字幕轨道才能显示字幕。如果需要关闭字幕功能，可以在字幕选择菜单中选择"无字幕"选项（如果可用）。

---

## 功能二：停止播放后自动返回文件列表

### 功能描述
当用户点击"⏹️ 停止并返回列表"按钮时，系统会停止当前播放并返回到之前的文件列表目录菜单界面。

### 技术实现
- **保持视频列表信息**：停止播放时，系统会保留当前目录的视频文件列表信息
- **智能返回**：根据用户之前浏览的目录，自动返回到对应的文件列表
- **不影响播放进度**：虽然返回了列表，但视频列表信息仍然保留，用户可以从列表中选择继续播放

### 使用方法
1. 在播放控制菜单中点击"⏹️ 停止并返回列表"
2. 系统会自动停止当前播放
3. 自动返回到之前的文件列表目录界面
4. 用户可以继续浏览其他文件或重新选择播放

### 注意事项
- 如果当前没有浏览过任何目录，会提示用户先选择视频目录
- 点击"◀️ 返回主菜单"会直接返回主菜单，不会返回文件列表

---

## 功能二：上一集/下一集快速切换

### 功能描述
在播放菜单中添加了"⬅️ 上一集"和"下一集 ➡️"按钮，方便用户在同目录下的多个视频之间快速切换。

### 功能特性

#### 1. **智能显示**
- 仅在当前目录存在多个视频文件时显示上一集/下一集按钮
- 如果目录只有1个视频，按钮不会显示

#### 2. **循环播放**
- 最后一个视频的"下一集"会自动切换到第一个视频
- 第一个视频的"上一集"会自动切换到最后一个视频
- 支持无缝循环播放

#### 3. **视觉反馈**
- 点击按钮时会有明确的提示："正在播放上一集..." 或 "正在播放下一集..."
- 自动更新播放状态显示
- 保持按钮状态（始终可点击）

### 使用方法

#### 切换到下一集
1. 在播放控制菜单中点击"下一集 ➡️"
2. 系统会自动停止当前视频
3. 自动播放同目录下的下一个视频
4. 如果当前是最后一个视频，会循环到第一个视频

#### 切换到上一集
1. 在播放控制菜单中点击"⬅️ 上一集"
2. 系统会自动停止当前视频
3. 自动播放同目录下的上一个视频
4. 如果当前是第一个视频，会循环到最后一个视频

### 播放顺序

假设目录中有以下视频文件：
```
📁 我的剧集/
   ├── 🎬 第01集.mp4
   ├── 🎬 第02集.mp4
   ├── 🎬 第03集.mp4
   ├── 🎬 第04集.mp4
   └── 🎬 第05集.mp4
```

**播放顺序示例：**
- 在第01集时点击"下一集" → 播放第02集
- 在第02集时点击"上一集" → 播放第01集
- 在第05集时点击"下一集" → 循环播放第01集
- 在第01集时点击"上一集" → 循环播放第05集

### 技术实现

#### 文件浏览模块 (file_browser.py)
```python
def get_next_video(self, current_file_path: str) -> Optional[FileItem]:
    """获取下一个视频文件（循环）"""
    video_files = self.get_all_video_files()
    if not video_files:
        return None

    current_index = self.get_video_file_index(current_file_path)
    if current_index == -1:
        return video_files[0] if video_files else None

    next_index = (current_index + 1) % len(video_files)
    return video_files[next_index]
```

#### VLC播放器模块 (vlc_player.py)
```python
def open_file(self, file_path: str, video_list: list = None, current_index: int = -1):
    """打开视频文件"""
    # 设置视频列表信息以支持上一集/下一集功能
    if video_list is not None:
        self.video_list = video_list
    if current_index >= 0:
        self.current_video_index = current_index
```

#### 主程序模块 (main.py)
```python
# 上一集/下一集按钮
if show_episode_buttons:
    keyboard.append([
        InlineKeyboardButton("⬅️ 上一集", callback_data="prev_episode"),
        InlineKeyboardButton("下一集 ➡️", callback_data="next_episode")
    ])
```

### 常见问题

#### Q: 为什么没有显示上一集/下一集按钮？
**A:** 按钮仅在当前目录存在多个视频文件时显示。如果目录只有1个视频，按钮不会显示。

#### Q: 切换集数后，之前的播放进度会丢失吗？
**A:** 当前实现会自动从头开始播放新选择的视频。如果需要保留播放进度，可以在未来版本中添加进度保存功能。

#### Q: 如何实现连续播放？
**A:** 使用上一集/下一集按钮可以手动实现连续播放。系统会在最后一个视频播放完毕后，用户手动切换到下一个视频。

#### Q: 播放列表是基于什么排序的？
**A:** 播放列表按照文件浏览器中的排序显示，通常是按文件名字母顺序排列。

---

## 更新日志

### v1.1.0 (2026-03-30)
- ✨ 新增：停止播放后自动返回文件列表功能
- ✨ 新增：上一集/下一集快速切换功能
- ✨ 新增：循环播放支持
- 🐛 修复：视频列表信息保留问题

---

## 未来计划

- [ ] 添加播放进度保存功能
- [ ] 支持自动连续播放
- [ ] 添加播放队列管理
- [ ] 支持播放历史记录
