"""
管理员账号系统
- 主管理员（super_admin）：可添加/删除管理员，管理所有租户
- 管理员（admin）：绑定中金或国关租户
"""
import hashlib
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.json"

# 主管理员初始密码的 SHA256
DEFAULT_ADMIN = "admin"
DEFAULT_PASS = hashlib.sha256("admin123".encode()).hexdigest()


def _load_users():
    """加载用户数据"""
    if USERS_FILE.exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 初始化：只有主管理员
    users = {
        DEFAULT_ADMIN: {
            "password": DEFAULT_PASS,
            "role": "super_admin",
            "tenant": None,
            "created_at": "",
        }
    }
    _save_users(users)
    return users


def _save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def verify_login(username: str, password: str):
    # type: (str, str) -> dict or None
    """验证登录，成功返回用户信息，失败返回 None"""
    users = _load_users()
    user = users.get(username)
    if not user:
        return None
    if user["password"] != hash_password(password):
        return None
    return {**user, "username": username}


def get_users() -> list:
    """获取所有用户列表（不含密码哈希）"""
    users = _load_users()
    return [
        {"username": u, "role": d["role"], "tenant": d["tenant"], "created_at": d.get("created_at", "")}
        for u, d in users.items()
    ]


def add_user(username, password, role, tenant=None):
    """添加管理员，返回 (success, message)"""
    users = _load_users()
    if username in users:
        return False, "用户名已存在"
    if not username or len(username) < 2:
        return False, "用户名至少2个字符"
    if not password or len(password) < 4:
        return False, "密码至少4位"
    if role not in ("admin", "super_admin"):
        return False, "角色无效"

    from datetime import datetime
    users[username] = {
        "password": hash_password(password),
        "role": role,
        "tenant": tenant,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_users(users)
    return True, "添加成功"


def delete_user(username):
    """删除用户，返回 (success, message)"""
    if username == DEFAULT_ADMIN:
        return False, "不能删除主管理员"
    users = _load_users()
    if username not in users:
        return False, "用户不存在"
    del users[username]
    _save_users(users)
    return True, "删除成功"


def update_user(username, new_username=None, new_password=None, new_tenant=None):
    """修改管理员用户名/密码/租户，返回 (success, message)"""
    users = _load_users()
    user = users.get(username)
    if not user:
        return False, "用户不存在"
    if user["role"] == "super_admin":
        return False, "不能修改主管理员"
    if new_password:
        users[username]["password"] = hash_password(new_password)
    if new_tenant:
        users[username]["tenant"] = new_tenant
    if new_username and new_username != username:
        if new_username in users:
            return False, "新用户名已存在"
        users[new_username] = users.pop(username)
    _save_users(users)
    return True, "修改成功"


def change_password(username, old_pwd, new_pwd):
    """修改密码，返回 (success, message)"""
    users = _load_users()
    user = users.get(username)
    if not user:
        return False, "用户不存在"
    if user["password"] != hash_password(old_pwd):
        return False, "旧密码错误"
    if len(new_pwd) < 4:
        return False, "新密码至少4位"
    users[username]["password"] = hash_password(new_pwd)
    _save_users(users)
    return True, "密码修改成功"
