# 前端素材提交 OSS

## 1. 准备

- 在项目根目录准备 `.env`。
- `.env` 中配置 `STORAGE_BACKEND=oss` 和 OSS 参数。
- AccessKey 只放在 `.env` 或密钥管理中，不写入脚本，不提交 Git。
- 将素材放入 `frontend/assets/`。

## 2. 检查和上传

```bash
# 检查 OSS 配置，不上传
bash docs/oss-frontend-assets/upload_frontend_assets_to_oss.sh --check

# 预览本地素材
bash docs/oss-frontend-assets/upload_frontend_assets_to_oss.sh --dry-run

# 正式上传
bash docs/oss-frontend-assets/upload_frontend_assets_to_oss.sh
```

脚本会按 `OSS_ASSET_PREFIX` 上传，例如：

```text
frontend/assets/workbench/icons/nav-desk.png
→ assets/workbench/icons/nav-desk.png
```

脚本只上传，不自动删除 OSS 旧对象。删除前请单独确认。

## 3. OSS 测试结果

已实测临时 WebP 图片的上传、读取和删除，3 个图片变体均通过，测试对象已清理。
