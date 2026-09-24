# Yumeiro · AstrBot Pixiv 插画插件

Yumeiro 是一个 AstrBot 插件，用自然语言从 Pixiv 发现并发送插画。Plugin Pages `Yumeiro Control` 仅用于管理配置、诊断和查看状态；实际搜索和发送发生在聊天中。

## 功能

- Pixiv App API Refresh Token 登录
- 默认使用 Pixiv 标签部分匹配搜索
- AstrBot LLM Tool 自然语言触发
- `/pixiv` 备用命令
- 可选画师 User ID 随机选图
- 可选指定插画 ID 或 Pixiv 作品链接发送
- R-18 / R-18G 默认过滤
- 图片临时下载、Pixiv 图片源校验、单文件大小限制和发送后自动清理
- 有界内存元数据缓存（不缓存图片文件）、按会话/用户冷却和全局并发下载限制
- 每日请求/成功发送统计、缓存状态及 Pixiv/API/安全图片下载诊断
- Plugin Pages 配置写入真实插件配置
- 配置、连接测试、诊断和缓存操作

## 安装

将插件目录放入 `AstrBot/data/plugins/astrbot_plugin_pixiv_gallery`，安装 `requirements.txt`，然后重载插件。

## 配置

在 AstrBot 插件配置或 Yumeiro Control Pages 中配置 `refresh_token`。Refresh Token 是敏感信息，不会返回到 Pages，也不会写入日志。

默认安全行为：

- `filter_r18: true`
- `filter_r18g: true`
- `enable_artist_random: false`
- `enable_illust_id_send: false`
- 未知或缺失安全等级默认拒绝；私聊/群聊授权不会覆盖启用的全局 R-18/R-18G 过滤

Pages 保存配置时由后端校验范围，并写入 AstrBot 的插件配置对象后调用 `save_config()`。

## 使用示例

```text
来几张黄昏海边的治愈系插画
找 3 张雨夜电车的蓝色系作品
/pixiv 星空壁纸
```

开启对应高级开关后：

```text
随机发一张画师 123456 的作品
发送 Pixiv 插画 123456789
发送 https://www.pixiv.net/artworks/123456789
```

指定 ID 不会绕过内容安全策略。`default_count` 是默认候选作品数（1–10）；`max_count` 是跨作品累计的单次图片页数上限（1–20），多图作品的每一页都计入。关闭“发送全部页面”时每个作品只取第一页。

## 搜索策略

普通自然语言请求会提取主题关键词，默认使用 `partial_match_for_tags`。画师 ID 请求使用 Pixiv 用户作品接口；插画 ID 请求使用作品详情接口。关键词、数量、中文/英文 Pixiv ID 与作品链接会在请求前校验；分页及图片数量均有上限。

## Pages

Page 名称为 `pixiv-gallery`，页面标题为 `Yumeiro Control`，包括总览、Pixiv 连接、对话行为、内容安全、缓存与限流、诊断和使用说明。诊断会实际检查鉴权/API、配置的网络路径及安全样例图片下载；消息链只检查构造能力，不代表聊天平台实际送达，需在目标聊天中验证。

## 隐私与版权

Refresh Token 只用于 Pixiv API 鉴权。作品版权归原作者和 Pixiv 相关权利方所有，请遵守 Pixiv、目标聊天平台及当地法律法规。

## 开发与验证

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
npm ci
npx playwright install chromium
npm run test:pages
```

Playwright 仅用于离线管理页面浏览器冒烟测试，不属于插件运行时依赖。
