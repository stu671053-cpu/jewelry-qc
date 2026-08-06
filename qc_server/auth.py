"""
管理员账号系统
- 主管理员（super_admin）：可添加/删除管理员，管理所有租户
- 管理员（admin）：绑定中金或国关租户
密码明文存储（内网系统，登录态保护）
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.json"

DEFAULT_ADMIN = "admin"
DEFAULT_PASS = "admin123"


def _load_users():
    if USERS_FILE.exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
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


def _save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def verify_login(username, password):
    users = _load_users()
    user = users.get(username)
    if not user or user["password"] != password:
        return None
    return {**user, "username": username}


def get_users():
    users = _load_users()
    return [
        {"username": u, "password": d["password"], "role": d["role"], "tenant": d["tenant"], "created_at": d.get("created_at", "")}
        for u, d in users.items()
    ]


def add_user(username, password, role, tenant=None):
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
        "password": password,
        "role": role,
        "tenant": tenant,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_users(users)
    return True, "添加成功"


def delete_user(username):
    if username == DEFAULT_ADMIN:
        return False, "不能删除主管理员"
    users = _load_users()
    if username not in users:
        return False, "用户不存在"
    del users[username]
    _save_users(users)
    return True, "删除成功"


def update_user(username, new_username=None, new_password=None, new_tenant=None):
    users = _load_users()
    user = users.get(username)
    if not user:
        return False, "用户不存在"
    if user["role"] == "super_admin":
        if new_password:
            users[username]["password"] = new_password
            _save_users(users)
            return True, "密码修改成功"
        return False, "主管理员只能修改密码"
    if new_password:
        users[username]["password"] = new_password
    if new_tenant:
        users[username]["tenant"] = new_tenant
    if new_username and new_username != username:
        if new_username in users:
            return False, "新用户名已存在"
        users[new_username] = users.pop(username)
    _save_users(users)
    return True, "修改成功"
