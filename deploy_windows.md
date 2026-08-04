# Windows Server 2012 内网部署指南

## 一、环境准备

### 1. 安装 Python 3.9+

下载地址：https://www.python.org/downloads/release/python-3913/
- ✅ 勾选 "Add Python to PATH"
- 安装完成后验证：`python --version`

### 2. 安装依赖

```cmd
cd C:\jewelry_qc
pip install -r requirements.txt
```

### 3. 创建项目目录

```
C:\jewelry_qc\
├── qc_server\          # Flask 主程序
│   ├── app.py
│   ├── db.py
│   ├── qc_service.py
│   ├── sync_service.py
│   ├── notifier.py
│   ├── utils.py
│   ├── templates\      # 前端页面
│   ├── config.json
│   ├── config_sync.json          # 中金 Cookie（从服务器复制）
│   └── config_sync_国关.json     # 国关 Cookie（从服务器复制）
├── rules\              # 规则引擎
├── engine.py
├── config.yaml
├── data\               # SQLite 数据库
│   ├── qic_quality.db         # 中金数据库
│   └── 国关_qic_quality.db    # 国关数据库
└── requirements.txt
```

### 4. 配置文件

从服务器复制以下文件到本地：

| 服务器路径 | 说明 |
|-----------|------|
| `qc_server/config_sync.json` | 中金 Loupe Cookie |
| `qc_server/config_sync_国关.json` | 国关 Loupe Cookie |
| `data/qic_quality.db` | 中金数据库（可选，会从 API 重新拉取）|
| `data/国关_qic_quality.db` | 国关数据库（可选）|

复制代码（从 GitHub）：
```cmd
git clone https://github.com/stu671053-cpu/jewelry-qc.git C:\jewelry_qc
```

---

## 二、运行方式

### 方式 A：NSSM 注册为 Windows 服务（推荐）

NSSM 下载：http://nssm.cc/download

```cmd
nssm install JewelryQC-Zhongjin
# Application Path: C:\Python39\python.exe
# Startup Directory: C:\jewelry_qc\qc_server
# Arguments: -m waitress --host 0.0.0.0 --port 5090 app:app
# 环境变量：TENANT=中金

nssm install JewelryQC-GuoGuan
# Application Path: C:\Python39\python.exe
# Startup Directory: C:\jewelry_qc\qc_server
# Arguments: -m waitress --host 0.0.0.0 --port 5091 app:app
# 环境变量：TENANT=国关
```

然后在「服务」中设置两个服务为「自动启动」。

### 方式 B：批处理 + 计划任务（简单）

创建 `start_zhongjin.bat`：
```bat
@echo off
cd /d C:\jewelry_qc\qc_server
set TENANT=中金
set PORT=5090
python -m waitress --host 0.0.0.0 --port 5090 app:app
```

创建 `start_guoguan.bat`：
```bat
@echo off
cd /d C:\jewelry_qc\qc_server
set TENANT=国关
set PORT=5091
python -m waitress --host 0.0.0.0 --port 5091 app:app
```

计划任务：创建两个任务，触发条件「系统启动时」，操作运行对应 bat 文件。

### 方式 C：Flask 自带服务器（仅测试）

```bat
cd /d C:\jewelry_qc\qc_server
set TENANT=中金
set PORT=5090
python app.py
```

⚠️ 自带服务器不适合生产环境，仅用于临时测试。

---

## 三、访问地址

| 租户 | 地址 |
|------|------|
| 中金大屏 | `http://{服务器IP}:5090/` |
| 中金管理端 | `http://{服务器IP}:5090/admin` |
| 国关大屏 | `http://{服务器IP}:5091/` |
| 国关管理端 | `http://{服务器IP}:5091/admin` |
| 中金健康检查 | `http://{服务器IP}:5090/api/health` |

---

## 四、维护操作

### 更新代码

```cmd
cd C:\jewelry_qc
git pull origin main
net stop JewelryQC-Zhongjin
net stop JewelryQC-GuoGuan
net start JewelryQC-Zhongjin
net start JewelryQC-GuoGuan
```

### 更新 Cookie

在 Loupe 系统重新登录后抓取 Cookie，替换 `config_sync.json` 和 `config_sync_国关.json` 中的 cookie 字段，然后重启服务。

### 查看日志

```cmd
# 若用 NSSM，日志在服务路径下
C:\jewelry_qc\qc_server\logs\qc_server.log

# 手动查看实时日志
python app.py  # 会有控制台输出
```

### 重置数据库

```cmd
del C:\jewelry_qc\data\qic_quality.db
del C:\jewelry_qc\data\国关_qic_quality.db
net stop JewelryQC-Zhongjin
net stop JewelryQC-GuoGuan
net start JewelryQC-Zhongjin
net start JewelryQC-GuoGuan
```
删除后重启服务，系统会从 Loupe API 重新全量拉取。

### 修改超时阈值

管理端 → 工作时间设置 → 剩余时间预警（分钟）

---

## 五、防火墙

确保内网防火墙放行 5090 和 5091 端口：

```cmd
netsh advfirewall firewall add rule name="JewelryQC 5090" dir=in action=allow protocol=TCP localport=5090
netsh advfirewall firewall add rule name="JewelryQC 5091" dir=in action=allow protocol=TCP localport=5091
```

---

## 六、目录结构确认

部署后检查以下文件必须存在：

```
C:\jewelry_qc\
├── engine.py              ✅
├── config.yaml            ✅
├── requirements.txt       ✅
├── rules/                 ✅ 14个文件
├── qc_server/
│   ├── app.py             ✅
│   ├── db.py              ✅
│   ├── qc_service.py      ✅
│   ├── sync_service.py    ✅
│   ├── notifier.py        ✅
│   ├── utils.py           ✅
│   ├── config.json        ✅
│   ├── config_sync.json   ⚠️ 需手动复制
│   ├── config_sync_国关.json  ⚠️ 需手动复制
│   └── templates/
│       ├── dashboard.html ✅
│       └── admin.html     ✅
└── data/
    ├── qic_quality.db         自动创建
    └── 国关_qic_quality.db    自动创建
```
