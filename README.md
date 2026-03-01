<div align="center">

# Lumina

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/crisocean/lumina?style=flat-square&logo=docker)](https://hub.docker.com/r/crisocean/lumina)
[![Vue 3](https://img.shields.io/badge/前端-Vue_3-4FC08D?style=flat-square&logo=vue.js)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/后端-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Version](https://img.shields.io/badge/版本-v1.6-orange?style=flat-square)](VERSION)

**现代化 Cloudflare WARP 管理面板**

[1.6 新增内容](#whats-new-16) • [核心特性](#core-features) • [快速开始](#quick-start) • [首次初始化](#first-setup) • [使用说明](#usage) • [安全说明](#security) • [开发调试](#dev)

---

![Lumina UI](resources/Lumina-02-02-2026_09_48_PM.png)

</div>

Lumina 是一个用于管理 Cloudflare WARP 的 Web 面板，支持 `usque` 与 `official` 双后端切换，提供连接控制、内核管理、日志查看、端口配置以及多节点统一管理能力。

<a id="whats-new-16"></a>

## 🚀 1.6 新增内容

- 新增 **多节点管理（Node Manager）**：集中查看本机和远程节点状态，并可远程执行连接/断开、后端切换。
- 新增 **安全中心（Security Center）**：会话数量查看、下线其他会话、当前会话登出、密码修改。
- 密码存储升级为 **bcrypt 哈希**，并支持旧明文密码自动迁移。
- 设置页整合：端口配置与安全能力在同一页面集中管理。

<a id="core-features"></a>

## ✨ 核心特性

- **双后端引擎**
  - `usque`：轻量高性能，默认推荐。
  - `official`：Cloudflare 官方客户端，兼容性优先。
  - 一键切换后端并自动重连。

- **连接与代理管理**
  - Web 一键 Connect / Disconnect。
  - SOCKS5 代理统一管理（默认 `127.0.0.1:1080`）。

- **多节点统一控制**
  - 节点列表/健康状态总览（版本、后端、IP、连接状态）。
  - 支持远程节点连接控制与后端切换。

- **内核版本管理**
  - 查看已安装版本、切换活跃版本、手动检查更新与升级（`usque`）。

- **实时可观测性**
  - WebSocket 实时状态与日志推送。
  - 日志筛选、搜索、下载。

- **安全能力**
  - 面板登录鉴权。
  - 会话管理（登出当前会话 / 下线其他会话）。
  - 密码 bcrypt 哈希存储，降低泄露风险。

## 🛠️ 技术栈

| 模块 | 技术 |
| :--- | :--- |
| 前端 | Vue 3 + Vite + Tailwind CSS v4 |
| 后端 | FastAPI + AsyncIO |
| 核心引擎 | usque / Cloudflare WARP 官方客户端 |
| 部署方式 | Docker / Linux 原生 |

<a id="quick-start"></a>

## 🚀 快速开始

### 前置要求

- Docker（Desktop 或 Engine）
- Linux 主机需支持 `/dev/net/tun`

### 方式一：使用预构建镜像（推荐）

仓库内已提供 `docker-compose.release.yml`：

```bash
docker compose -f docker-compose.release.yml up -d
```

### 方式二：源码构建镜像

```bash
git clone https://github.com/CrisRain/lumina.git
cd lumina
docker compose up --build -d
```

启动后访问：`http://localhost:8000`

<a id="first-setup"></a>

## ✅ 首次初始化（必做）

首次启动会自动进入 `/setup` 页面，请完成：

1. 设置管理员密码（至少 8 位）
2. （可选）修改 SOCKS5 端口与面板端口
3. 提交后进入登录页

说明：
- 初始化后配置保存在 `/app/data/config.db`。
- 面板密码以 bcrypt 哈希存储。

<a id="usage"></a>

## 📖 使用说明

### 1) Dashboard

- 查看当前连接状态、出口 IP、地区信息
- 一键连接与断开

### 2) Nodes（多节点管理）

- 新增远程节点（名称 + Base URL + 可选 Token）
- 统一查看本机/远程节点状态
- 对节点执行 `Connect` / `Disconnect` / 后端切换

### 3) Kernel

- 查看和切换 `usque` 版本
- 检查更新并执行升级

### 4) Settings

- 端口配置：SOCKS5 / Panel Port
- 安全中心：修改密码、会话管理、主动登出

### 5) Logs

- 实时日志、级别筛选、关键词搜索、下载日志

## 🌐 多节点配置建议

新增远程节点时，`Base URL` 示例：

- `http://192.168.1.10:8000`
- `https://node.example.com`

若远程节点开启了鉴权，需要填入 Token。你可以在远程节点上通过登录接口获取：

```bash
curl -X POST "http://REMOTE_NODE:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"password":"YOUR_PANEL_PASSWORD"}'
```

返回示例：

```json
{"success": true, "token": "xxxxx"}
```

将该 `token` 填入 Node Manager 即可。

<a id="security"></a>

## 🔒 安全说明

- SOCKS5 默认绑定 `127.0.0.1`，不直接暴露公网。
- 若需远程使用代理，推荐 SSH 隧道：

```bash
ssh -L 1080:127.0.0.1:1080 your-server-ip
```

- 密码采用 bcrypt 哈希存储；旧明文密码会在启动时自动迁移。

## 🐧 Linux 原生部署

```bash
git clone https://github.com/CrisRain/lumina.git
cd lumina
chmod +x linux_install.sh
sudo ./linux_install.sh
```

常用管理命令：

```bash
sudo supervisorctl status
sudo supervisorctl restart all
```

<a id="dev"></a>

## 💻 开发调试

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。
