# 项目结构

```
TgVLC_Bot/
│
├── 📄 配置文件
│   ├── config.yaml              # 主配置文件
│   └── .gitignore               # Git忽略配置
│
├── 📦 核心模块
│   ├── config.py               # 配置管理模块
│   ├── file_browser.py         # 文件浏览器模块
│   ├── vlc_player.py           # VLC播放器控制模块
│   └── main.py                 # Telegram机器人主程序
│
├── 📚 文档
│   ├── README.md               # 项目说明文档
│   └── QUICKSTART.md           # 快速开始指南
│
├── 🔧 脚本
│   └── setup.bat               # 快速启动脚本
│
└── 📋 依赖
    └── requirements.txt        # Python依赖清单
```

## 模块说明

### config.py
配置管理模块，负责从 config.yaml 读取和保存系统配置。

**主要功能：**
- 配置加载和保存
- 视频目录管理
- 用户权限管理
- 代理配置

### file_browser.py
文件浏览器模块，提供视频文件的浏览和导航功能。

**主要功能：**
- 目录浏览
- 分页显示
- 文件过滤
- 层级导航

### vlc_player.py
VLC播放器控制模块，管理VLC播放器的运行和控制。

**主要功能：**
- 播放器初始化
- 播放控制
- 音量控制
- 进度控制
- 全屏切换
- 窗口激活

### main.py
Telegram机器人主程序，处理用户交互和控制流程。

**主要功能：**
- 命令处理
- 状态管理
- 按钮交互
- 权限验证

## 文件用途

| 文件 | 说明 |
|------|------|
| config.yaml | 存储所有配置信息（Token、路径、权限等） |
| requirements.txt | Python依赖包列表 |
| README.md | 详细的项目说明文档 |
| QUICKSTART.md | 5分钟快速上手指南 |
| setup.bat | 一键启动脚本 |

## 配置管理

所有配置信息存储在 `config.yaml` 中：

```yaml
telegram:
  token: "YOUR_BOT_TOKEN"

proxy:
  enabled: false
  type: "socks5"
  host: "127.0.0.1"
  port: 1080

vlc:
  path: "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"

video:
  directories:
    - "D:\\Movies"

controls:
  volume_step: 10
  seek_step: 30
  page_size: 10

security:
  allowed_user_ids: []
  admin_user_ids:
    - 123456789
```

## 启动流程

1. 安装依赖：`pip install -r requirements.txt`
2. 配置 config.yaml
3. 运行程序：`python main.py` 或双击 setup.bat
