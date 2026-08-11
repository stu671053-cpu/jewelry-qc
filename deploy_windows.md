# 珠宝检测AI自查系统 - 内网部署指南

## 快速部署（3 步搞定）

### 第 1 步：安装 Python

下载 Python 3.9+ 安装包 → 安装时勾选 **"Add Python to PATH"**

安装完成打开 CMD 验证：
```cmd
python --version
```
应显示 `Python 3.9.x` 或更高。

### 第 2 步：解压并安装依赖

将 `jewelry_qc_deploy.zip` 解压到 `C:\jewelry_qc`，打开 CMD 执行：

```cmd
cd C:\jewelry_qc
pip install -r requirements.txt
```

### 第 3 步：启动服务

双击桌面上的快捷方式（或直接双击 bat 文件）：

| 快捷方式 | 端口 | 说明 |
|----------|------|------|
| `start_zhongjin.bat` | 5090 | 中金租户 |
| `start_guoguan.bat` | 5091 | 国关租户 |

启动后会打开两个 CMD 窗口，**最小化即可**，不要关闭。

内网其他电脑访问：`http://服务器IP:5090/`（中金）或 `http://服务器IP:5091/`（国关）

---

## 目录结构

```
C:\jewelry_qc\
├── start_zhongjin.bat        ← 双击启动中金 (5090)
├── start_guoguan.bat         ← 双击启动国关 (5091)
├── requirements.txt           ← Python 依赖
├── qc_server\                 ← 主程序
│   ├── app.py                 ← Flask 入口
│   ├── db.py                  ← 数据库操作
│   ├── qc_service.py          ← 质检规则引擎
│   ├── auth.py                ← 管理员登录验证
│   ├── utils.py               ← 工具函数
│   ├── config_sync.json       ← 中金 Cookie 配置
│   ├── config_sync_国关.json  ← 国关 Cookie 配置
│   ├── users.json             ← 管理员账号
│   └── templates\             ← 前端页面
├── rules\                     ← 质检规则（R1-R12）
├── engine.py                  ← 规则加载引擎
└── data\                      ← 数据库文件（自动创建）
```

---

## 管理员账号

管理后台地址：`http://服务器IP:5090/login`

| 角色 | 用户名 | 密码 | 权限 |
|------|--------|------|------|
| 主管理员 | `admin` | `admin123` | 全部管理 |
| 中金管理员 | `zhongjin` | `zj1234` | 仅中金 |
| 国关管理员 | `guoguan` | `gg1234` | 仅国关 |

> 主管理员登录后可添加/删除/修改其他管理员账号。

---

## 日常维护

### 更新代码
```cmd
cd C:\jewelry_qc
git pull
:: 关闭两个 CMD 窗口，重新双击 bat 文件启动
```

### 更新 Cookie
用新 Cookie 替换 `qc_server\config_sync.json` 或 `config_sync_国关.json` 中的 `cookie` 字段，重启服务。

### 修改超时预警阈值
管理端 → 系统设置 → 修改「剩余时间预警（分钟）」→ 保存

### 重置数据库
```cmd
cd C:\jewelry_qc
del data\*.db
:: 重启服务即可，系统会自动重建数据库并重新检测
```

---

## 防火墙配置

如果内网其他电脑无法访问，需要在 Windows 防火墙放行端口：

```cmd
netsh advfirewall firewall add rule name="jewelry_qc_5090" dir=in action=allow protocol=tcp localport=5090
netsh advfirewall firewall add rule name="jewelry_qc_5091" dir=in action=allow protocol=tcp localport=5091
```

---

## 常见问题

**Q: 启动后 CMD 一闪而过？**
A: 在 bat 文件所在目录打开 CMD，手动运行 `python qc_server\app.py` 查看错误信息。

**Q: 提示 `ModuleNotFoundError`？**
A: `pip install -r requirements.txt` 重新安装依赖。

**Q: 数据不更新？**
A: 检查 Cookie 是否过期，管理端查看系统状态 → 运行日志。
