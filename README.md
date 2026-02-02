# WarpPanel

WarpPanel 是一个现代化的 Web 控制面板，专为管理单实例 Cloudflare WARP 客户端而设计。它提供了一个极具质感的响应式界面，让您可以轻松连接、断开 WARP，并实时监控连接状态。

## ✨ 功能特性

- **🎯 单实例管理**：精准控制您的 WARP 容器，状态实时同步。
- **🎨 极致 UI 设计**：基于 Vue 3 和 Tailwind CSS v4 构建，采用磨砂玻璃拟态（Glassmorphism）风格，动画流畅丝滑。
- **⚡ 实时监控**：通过 WebSocket 实现秒级状态更新，即时获取连接反馈。
- **🔄 一键 IP 轮换**：支持简单的 IP 轮换功能（自动断开重连），快速获取新 IP。
- **📊 详细连接信息**：直观展示 IP 地址、城市、国家/地区、ISP 供应商、协议类型及端点信息。
- **📝 系统日志**：内置实时日志查看器，方便排查问题和监控运行状态。
- **🔒 SOCKS5 代理**：内置 SOCKS5 代理服务（默认端口 `1080`），方便其他应用接入。

## 🛠️ 技术栈

- **前端**: Vue 3 + Vite + Tailwind CSS (v4)
- **后端**: FastAPI (Python)
- **容器化**: Docker + Docker Compose

## 📸 效果预览

![WarpPanel UI](resources/WarpPanel-02-02-2026_09_48_PM.png)

## 🚀 快速开始

### 前置要求

- Docker Desktop (或 Docker Engine + Docker Compose)
- Git

### 安装步骤

1. 克隆项目仓库：

```bash
git clone https://github.com/CrisRain/warppanel.git
cd warppanel
```

2. 使用 Docker Compose 构建并启动服务：

```bash
docker-compose up --build -d
```

3. 访问 Web 界面：打开浏览器访问 **http://localhost:5173**

### 端口说明

- **Web UI**: 5173
- **API**: 8000
- **SOCKS5 Proxy**: 1080

## 📖 使用说明

1. **建立连接**：点击界面中央巨大的 **Connect** 按钮启动 WARP 连接。
2. **查看状态**：连接成功后，卡片将显示您的实时 IP、地理位置和 ISP 信息。
3. **复制代理**：在 Proxy Address 卡片中，点击 "Copy" 按钮即可快速复制 SOCKS5 代理地址。
4. **轮换 IP**：点击底部的 **Rotate IP** 按钮，系统将自动重置连接以获取新的 IP 地址。
5. **查看日志**：点击 "Service Logs" 卡片可以进入详细日志页面或在首页预览最近的系统活动。

## 💻 开发指南

### 前端开发
```bash
cd frontend
npm install
npm run dev
```

### 后端开发
```bash
cd controller-app
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 📄 许可证

MIT License - 欢迎个人学习与使用。