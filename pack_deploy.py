#!/usr/bin/env python3
"""内网部署包打包脚本"""
import os, shutil, zipfile, fnmatch
from pathlib import Path

ROOT = Path(__file__).parent
BUILD = ROOT / "jewelry_qc_deploy"
ZIP_NAME = ROOT / "jewelry_qc_deploy.zip"

# 排除的 glob 模式（相对于项目根目录）
EXCLUDE_PATTERNS = [
    "__pycache__",
    "__pycache__/*",
    ".DS_Store",
    "*.pyc",
    "*.mdb",
    "*.csv",
    "*.zip",
    "*.pem",
    "data/*.db",
    "data/*.db-*",
    "qc_server/data/*",
    "qc_server/*.db",
    "qc_server/*.db-*",
    "qc_server/settings.json",
    "qc_server/sync_state.json",
    "qc_server/sync_state.*",
    "qc_server/users.json.bak",
    "qc_server/config_sync.example.json",
    "qc_server/requirements.txt",
    "qc_server/*mock*",
    "qc_server/get_chatid.py",
    "qc_server/har_parser.py",
    "qc_server/jewelry-qc.service",
    "qc_server/.DS_Store",
    "rules/__pycache__",
    "rules/__pycache__/*",
    "rules/qic-api",
    "rules/*.pyc",
    ".git",
    ".git/*",
    ".gitignore",
    ".venv",
    ".venv/*",
    ".workbuddy",
    ".workbuddy/*",
    ".pytest_cache",
    ".pytest_cache/*",
    "tests",
    "tests/*",
    "assets",
    "assets/*",
    "自动录入插件",
    "自动录入插件/*",
    "自动录入插件 2.zip",
    "qc_web.html",
    "API接口文档.md",
    "API字段映射_导出表.xlsx",
    "deploy_server.sh",
    "deploy_tv.sh",
    "pack_deploy.py",
    ".codebuddy",
    ".codebuddy/*",
    "超时预警_独立脚本说明.md",
    "jewelry_qc_deploy",
    "jewelry_qc_deploy/*",
    "jewelry_qc_deploy.zip",
    "datebase - 26-7-27.mdb",
]

def is_excluded(rel_path: str) -> bool:
    for pat in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(rel_path, pat):
            return True
        if fnmatch.fnmatch(os.path.basename(rel_path), pat):
            return True
        # 也匹配路径中的任意层级
        parts = rel_path.replace("\\", "/").split("/")
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False

print("📦 打包 jewelry_qc 内网部署包...")

if BUILD.exists():
    shutil.rmtree(BUILD)
BUILD.mkdir(parents=True)
(BUILD / "data").mkdir(exist_ok=True)

file_count = 0
for root, dirs, files in os.walk(ROOT):
    # 过滤目录
    dirs[:] = [d for d in dirs if not is_excluded(
        os.path.relpath(os.path.join(root, d), ROOT) + "/")]
    
    for f in files:
        fp = os.path.join(root, f)
        rel = os.path.relpath(fp, ROOT)
        
        if is_excluded(rel):
            continue
        
        dst = BUILD / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fp, dst)
        file_count += 1

if ZIP_NAME.exists():
    ZIP_NAME.unlink()

with zipfile.ZipFile(ZIP_NAME, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(BUILD):
        for f in files:
            fp = Path(root) / f
            arcname = fp.relative_to(BUILD)
            zf.write(fp, arcname)

size_mb = ZIP_NAME.stat().st_size / (1024 * 1024)
print(f"\n✅ 打包完成！")
print(f"   文件数: {file_count}")
print(f"   输出: {ZIP_NAME.name}")
print(f"   大小: {size_mb:.1f} MB")
print(f"\n📋 部署步骤:")
print(f"   1. 将 {ZIP_NAME.name} 复制到目标服务器")
print(f"   2. 解压到 C:\\jewelry_qc")
print(f"   3. 双击 start.bat（自动检测环境+安装依赖+启动双服务）")
print(f"   4. 内网访问: http://服务器IP:5090/ 和 :5091/")
