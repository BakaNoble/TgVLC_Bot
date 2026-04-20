# 快速启动指南

## 🚀 5分钟快速上手

### 第一步：安装依赖（1分钟）

```bash
pip install -r requirements.txt
```

### 第二步：配置 Telegram Bot Token（2分钟）

1. 在 Telegram 中搜索 **@BotFather**
2. 发送 `/newbot`
3. 设置机器人名称（如：我的VLC控制器）
4. 设置用户名（必须以 bot 结尾，如：myvlc_bot）
5. 复制获得的 Token

编辑 `config.yaml` 文件：
```yaml
telegram:
  token: "粘贴你的Token在这里"
```

### 第三步：启动系统（1分钟）

```bash
python main.py
```

### 第四步：开始使用（1分钟）

1. 在 Telegram 中找到你的机器人
2. 发送 `/start`
3. 选择操作开始控制！

## 📋 首次配置清单

- [ ] Telegram Bot Token 已配置
- [ ] VLC 已安装
- [ ] 至少一个视频目录已配置
- [ ] （可选）添加管理员用户ID

## ⚙️ 快速配置示例

### 基础配置
```yaml
telegram:
  token: "YOUR_TOKEN"

video:
  directories:
    - "D:\\Movies"
```

### 代理配置
```yaml
proxy:
  enabled: true
  type: "socks5"
  host: "127.0.0.1"
  port: 1080
```

### 管理员配置
```yaml
security:
  admin_user_ids:
    - 你的Telegram用户ID
```

## 🎮 常用操作

### 浏览视频
1. 点击"📂 浏览视频"
2. 选择配置的视频目录
3. 点击子目录继续深入
4. 点击视频文件开始播放

### 播放控制
- 播放/暂停 - 切换播放状态
- 前进/后退 - 跳转30秒
- 音量调节 - 增减音量
- 全屏切换 - 切换显示模式

## 🔧 常见问题

### "VLC 初始化失败"
- 检查 VLC 是否已安装
- 确认 config.yaml 中的路径正确

### "机器人无响应"
- 检查 Token 是否正确
- 检查网络连接
- 查看命令行错误信息

## 📞 获取帮助

遇到问题？
1. 查看 README.md 详细文档
2. 检查命令行错误信息
3. 确认配置文件格式正确

---

**祝你使用愉快！🎬**
