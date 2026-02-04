<div align="center">

# WarpPanel

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/crisocean/warppanel?style=flat-square&logo=docker)](https://hub.docker.com/r/crisocean/warppanel)
[![Vue 3](https://img.shields.io/badge/Frontend-Vue_3-4FC08D?style=flat-square&logo=vue.js)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)

**现代化的 Cloudflare WARP 单实例管理面板**

[功能特性](#-功能特性) • [技术栈](#-技术栈) • [快速开始](#-快速开始) • [使用指南](#-使用说明)

---

![WarpPanel UI](resources/WarpPanel-02-02-2026_09_48_PM.png)

</div>

**WarpPanel** 是一款专为管理 Cloudflare WARP 客户端设计的现代化 Web 控制面板。它拥有极具质感的 **Glassmorphism (磨砂玻璃)** 风格界面，提供流畅的交互体验，支持在 **Official** 与 **usque** 双核引擎间无缝切换，助您轻松掌控网络连接。

## ✨ 功能特性

- **🎯 单实例精细管理**
  精准控制 WARP 容器，状态实时同步，极低资源占用，适合个人 VPS 或本地环境部署。

- **🔄 无缝双核架构 (Dual Backend)**
  WarpPanel 独创支持双内核一键热切换，无需重启容器：
  - **`usque` (MASQUE)**: 高性能、轻量级的 Go 实现，连接速度极快，资源占用极低（**默认推荐**）。
  - **`official`**: Cloudflare 官方 Linux 客户端，拥有最强的兼容性和原生特性支持。

- **⚡ 极致性能与响应**
  - **零阻塞架构**: 后端采用全异步非阻塞设计，耗时操作（连接、检测）均在后台线程池执行。
  - **实时监控**: 基于 WebSocket 推送，秒级响应连接状态变化。

- **🎨 沉浸式 UI 设计**
  基于 Vue 3 + Tailwind CSS v4 构建，全响应式布局，配合丝滑的过渡动画，提供顶级的视觉体验。

- **🛡️ 隐私与智能**
  - **纯净日志**: 智能屏蔽冗余的底层连接日志，仅展示关键业务信息。
  - **智能 IP 轮换**: 一键断开重连以获取新 IP，内置连通性检测。
  - **SOCKS5 代理**: 内置标准 SOCKS5 服务（默认端口 `1080`），即插即用。

## 🛠️ 技术栈

| 模块 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| **Frontend** | Vue 3, Vite, Tailwind CSS v4 | 现代化组件开发，极致构建速度，原子化 CSS |
| **Backend** | Python 3.10+, FastAPI, AsyncIO | 高性能异步 Web 框架，稳定可靠 |
| **Core** | Cloudflare WARP Official + usque | 官方稳定版与社区高性能版双剑合璧 |
| **Deploy** | Docker, Docker Compose | 一键容器化部署，开箱即用 |

## 🚀 快速开始

### 前置要求
- **Docker** (Desktop 或 Engine)
- **Git** (仅源码构建需要)

### 方式一：Docker Hub 快速启动 (推荐)

无需构建代码，直接使用预构建镜像即可运行。

1. **创建 `docker-compose.yml` 文件**

```yaml
version: '3.8'

services:
  warp:
    image: crisocean/warppanel:latest
    container_name: warppanel
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun
    environment:
      - WARP_BACKEND=usque # 可选: 'usque' (默认,高性能) 或 'official' (官方客户端)
    sysctls:
      - net.ipv6.conf.all.disable_ipv6=0
    ports:
      - "5173:8000" # Web 控制台
      - "1080:1080" # SOCKS5 代理端口
    volumes:
      - warp_data:/var/lib/cloudflare-warp
      - ./warp_config:/var/lib/warp # usque 配置文件持久化 (建议挂载)

volumes:
  warp_data:
```

2. **启动服务**

```bash
docker-compose up -d
```

### 方式二：从源码构建

如果您想进行二次开发或自定义构建：

```bash
# 1. 克隆项目
git clone https://github.com/CrisRain/warppanel.git
cd warppanel

# 2. 构建并启动
docker-compose up --build -d
```

启动完成后，请访问浏览器：**[http://localhost:5173](http://localhost:5173)**

---

## 📖 使用说明

1.  **建立连接**
    点击界面中央巨大的 **Connect** 按钮即可启动 WARP 连接。连接过程纯后台异步执行，界面不会卡顿。

2.  **切换内核 (Backend Switching)**
    在右上角菜单中选择 **Usque** 或 **Official**。系统将自动处理旧进程清理、端口释放与新服务启动，全程无需人工干预。

3.  **查看状态**
    连接成功后，卡片将实时显示您的：
    - 🌍 **IP 地址** & **地理位置**
    - 🏢 **ISP 供应商**
    - 📡 **协议类型** (WireGuard/MASQUE)

4.  **IP 轮换**
    点击底部的 **Rotate IP** 按钮，系统将尝试断开并重新握手以获取新的 IP 地址。

5.  **查看日志**
    点击 **"Service Logs"** 卡片进入日志页。系统会自动过滤掉底层的 "Connection open/closed" 等噪音，只为您展示关键的连接与错误信息。

## 💻 开发指南

<details>
<summary>点击展开开发环境配置</summary>

### 前端开发 (Frontend)
```bash
cd frontend
npm install
npm run dev
```

### 后端开发 (Backend)
```bash
cd controller-app
pip install -r requirements.txt
uvicorn app.main:app --reload
```

</details>

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。欢迎 Star 与 Fork！