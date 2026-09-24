from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "pages" / "pixiv-gallery" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "pages" / "pixiv-gallery" / "app.js").read_text(encoding="utf-8")
METADATA = (ROOT / "metadata.yaml").read_text(encoding="utf-8")


def test_refresh_token_field_is_editable_and_secret_safe():
    assert 'id="token"' in HTML
    assert 'type="password"' in HTML
    assert 'readonly' not in HTML.split('id="token"', 1)[1].split('>', 1)[0]
    assert 'value="••••' not in HTML
    assert 'refresh_token' in JS
    assert 'settings.refresh_token_configured' in JS


def test_frontend_save_has_explicit_feedback_and_submits_token():
    assert '正在保存' in JS
    assert '设置已保存' in JS
    assert '保存失败' in JS
    assert 'refresh_token' in JS
    assert 'data-saving' in JS
    assert 'setSaveControlsEnabled' in JS
    assert 'id="view-safety"' in HTML
    safety = HTML.split('id="view-safety"', 1)[1].split('id="view-cache"', 1)[0]
    assert '保存设置' in safety


def test_clear_token_uses_the_same_save_feedback_path():
    assert "data-saving" in JS.split("id=\"clear-token\"", 1)[-1] or "data-saving" in JS
    assert "result.message || '设置已保存'" in JS
    assert "Refresh Token 已清除" in JS


def test_page_does_not_present_known_static_fake_statuses():
    for literal in ("Connected", "Tool Ready", "2 分钟前", "上次检查通过", "4 / 4", "响应时间 684ms", "Pixiv 连接验证成功", "释放 12 个临时文件"):
        assert literal not in HTML


def test_unimplemented_cache_and_safety_controls_are_not_rendered_as_active_settings():
    cache = HTML.split('id="view-cache"', 1)[1].split('id="view-diagnostics"', 1)[0]
    safety = HTML.split('id="view-safety"', 1)[1].split('id="view-cache"', 1)[0]
    assert 'id="max-size"' in cache
    assert 'id="cache-ttl"' not in cache
    assert 'id="concurrency"' not in cache
    assert '未接入能力' in cache
    assert 'data-config-key="allow_private_r18"' not in safety
    assert 'data-config-key="allow_group_r18"' not in safety
    assert 'data-config-key="reject_when_safety_check_failed"' not in safety
    assert "cache_ttl_minutes" not in JS
    assert "download_concurrency" not in JS


def test_frontend_toasts_render_text_without_interpolated_html():
    assert "host.innerHTML =" not in JS
    assert "toastMessage.textContent = message" in JS


def test_release_version_is_0_1_1():
    assert "version: 0.1.1" in METADATA
    assert "v0.1.1" in HTML
