# 珠宝检测AI自查系统 - 内网部署指南

## 快速部署（2 步）

### 第 1 步：安装 Python

下载 Python 3.9+ → 安装时**必须勾选** `Add Python to PATH`

https://www.python.org/downloads/

### 第 2 步：解压 & 启动

把 `jewelry_qc_deploy.zip` 解压到 `C:\jewelry_qc`，双击 **`start.bat`**。

> 首次运行会自动检查环境并安装缺失的依赖包，全程无需手动操作。

---

## 访问地址

| 页面 | 地址 |
|------|------|
| 中金大屏 | `http://服务器IP:5090/` |
| 国关大屏 | `http://服务器IP:5091/` |
| 管理后台 | `http://服务器IP:5090/login` |

---

## 管理员账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 主管理员 | `admin` | `admin123` |
| 中金管理员 | `zhongjin` | `zj1234` |
| 国关管理员 | `guoguan` | `gg1234` |

---

## 日常维护

### 更新代码
用新的 `jewelry_qc_deploy.zip` **覆盖解压**到 `C:\jewelry_qc`（保留 `data\` 和 `users.json` 不会被覆盖），关闭 CMD 窗口后重新双击 `start.bat`。

> 若启动失败，`start.bat` 会自动打印错误日志的最后 40 行；也可手动查看 `C:\jewelry_qc\zj.log` / `gg.log`。

### 修改超时预警阈值
管理端 → 系统设置 → 修改「剩余时间预警（分钟）」→ 保存

### 重置数据库
删除 `C:\jewelry_qc\data\*.db`，重启 start.bat

---

## 防火墙

如果内网其他电脑无法访问：

```cmd
netsh advfirewall firewall add rule name="jewelry_qc_5090" dir=in action=allow protocol=tcp localport=5090
netsh advfirewall firewall add rule name="jewelry_qc_5091" dir=in action=allow protocol=tcp localport=5091
```
