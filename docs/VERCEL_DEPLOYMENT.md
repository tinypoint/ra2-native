# Vercel 网页与 Blob 资源托管

当前采用 Vercel 托管网页、加载器和清单，Vercel Blob 托管 Web 程序和游戏资源。
下载不经过 GitHub Releases，也不依赖 Tailscale。GitHub 仓库统一维护 macOS 与 Web 源码。

- 源码：https://github.com/tinypoint/ra2-native
- 网页：https://ra2-web-alpha.vercel.app/
- Vercel 项目：`ra2-web`，工作区 `tinypoints-projects`。
- Blob 存储：`ra2-assets`，Public，东京 `hnd1`。

## 准备与部署

```sh
.venv/bin/python tools/prepare_github_resources.py
.venv/bin/python tools/prepare_vercel_web.py --resources-repository tinypoint/ra2-native
.venv/bin/python tools/prepare_blob_assets.py
.venv/bin/python tools/upload_blob_assets.py
.venv/bin/python tools/prepare_vercel_web.py --resources-repository tinypoint/ra2-native --blob
.venv/bin/python tools/deploy_vercel_web.py
```

前两条是本地分块准备步骤，不上传 GitHub。历史命名会在后续清理；实际下载由 `--blob` 清单决定。
部署目录 `.local/vercel-site/` 约 660 KB，含页面、JS 加载器和清单，不含大程序包或原版资源。
Blob 上传目录和进度记录在 `.local/blob-assets/`，已成功上传的对象会被跳过。
部署工具通过现有关联项目的 Vercel API 部署；登录凭据均在忽略的 `.local/web-access/` 下。
不要上传工程根目录、原安装包或 `.local` 到 Git。

## 下载与缓存

原始游戏资源共 372,410,994 字节；当前程序压缩包约 24 MB。资源按 1 MiB 网络分段，
可压缩的分段使用 deflate；所有程序和资源的上传总量约 216 MB。网络分段组装为
原有 16 MiB IndexedDB 缓存块，并以 SHA-256 校验。已导入的原资源缓存身份不变。
程序下载分段也保留缓存；普通刷新不会重新下载已经完成的数据。
首次进入自动下载和启动，仍保留手机手动导入已有包的入口。
新域名不能直接读取 Tailscale 域名的 IndexedDB，首次可自动下载，或导入已有文件。

网页全站配置 COOP `same-origin`、COEP `require-corp`、CORP `same-origin`；
CSP 仅额外允许当前 Blob 存储域名的连接。Blob 公共读取支持 CORS；无需在网页暴露写入令牌。
静态源码与清单重新验证，Blob 不可变内容寻址下载使用一年缓存。诊断记录留在浏览器本地。

## 当前验证范围

网页 HTTP 200 和跨源隔离响应头已检查；Blob 程序样本下载、CORS 和 SHA-256 校验已检查。
上传完成状态以 `.local/blob-assets/uploaded.json` 与 `logs/vercel-blob-upload.log` 为准。
完整手机运行仍由用户验证，本次部署准备没有启动游戏测试。
