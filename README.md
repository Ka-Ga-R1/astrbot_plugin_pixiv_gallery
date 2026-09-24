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
- 图片临时下载、大小限制和自动清理
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

指定 ID 不会绕过内容安全策略。

## 搜索策略

普通自然语言请求会提取主题关键词，默认使用 `partial_match_for_tags`。画师 ID 请求使用 Pixiv 用户作品接口；插画 ID 请求使用作品详情接口。

## Pages

Page 名称为 `pixiv-gallery`，页面标题为 `Yumeiro Control`，包括总览、Pixiv 连接、对话行为、内容安全、缓存与限流、诊断和使用说明。

## 隐私与版权

Refresh Token 只用于 Pixiv API 鉴权。作品版权归原作者和 Pixiv 相关权利方所有，请遵守 Pixiv、目标聊天平台及当地法律法规。
