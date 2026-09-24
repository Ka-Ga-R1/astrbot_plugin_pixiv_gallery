const bridge = window.AstrBotPluginPage;
const panels = [...document.querySelectorAll('[data-view-panel]')];
const links = [...document.querySelectorAll('[data-view]')];
let toastTimer;
let loadedSettings = {};
let settingsReady = false;

function notify(message, error = false) {
  const host = document.querySelector('#toast');
  if (!host) return;
  const toastMessage = document.createElement('div');
  toastMessage.className = `toast-message ${error ? 'error' : ''}`;
  toastMessage.setAttribute('role', 'status');
  toastMessage.textContent = message;
  host.replaceChildren(toastMessage);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => host.replaceChildren(), 3200);
}

function showView(name) {
  const next = panels.some(panel => panel.dataset.viewPanel === name) ? name : 'overview';
  panels.forEach(panel => panel.classList.toggle('active', panel.dataset.viewPanel === next));
  document.querySelectorAll('.admin-nav-link').forEach(link => link.classList.toggle('active', link.dataset.view === next));
  history.replaceState(null, '', `#${next}`);
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (next === 'overview') loadStats();
}

async function apiGet(endpoint, params) {
  if (!bridge?.apiGet) throw new Error('当前页面尚未连接 AstrBot Bridge');
  return bridge.apiGet(endpoint, params);
}

async function apiPost(endpoint, body) {
  if (!bridge?.apiPost) throw new Error('当前页面尚未连接 AstrBot Bridge');
  return bridge.apiPost(endpoint, body);
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
}

function setBadge(selector, label, state = 'neutral') {
  const element = document.querySelector(selector);
  if (!element) return;
  element.classList.remove('success', 'warning', 'neutral', 'error');
  element.classList.add(state);
  element.innerHTML = `<i></i>${label}`;
}

function formatTimestamp(value) {
  if (!value) return '尚无记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' });
}

function applySettings(settings) {
  loadedSettings = { ...loadedSettings, ...settings };
  settingsReady = true;
  setSaveControlsEnabled(true);
  const fields = {
    proxy: '#proxy',
    timeout_seconds: '#timeout',
    default_count: '#count',
    max_file_size_mb: '#max-size',
  };
  Object.entries(fields).forEach(([key, selector]) => {
    const element = document.querySelector(selector);
    if (element && settings[key] !== undefined) element.value = settings[key];
  });
  document.querySelectorAll('[data-config-key]').forEach(element => {
    const key = element.dataset.configKey;
    if (settings[key] !== undefined) element.checked = Boolean(settings[key]);
  });

  const configured = Boolean(settings.refresh_token_configured);
  const token = document.querySelector('#token');
  if (token) token.value = '';
  const configuredBadge = document.querySelector('#token-configured');
  if (configuredBadge) configuredBadge.textContent = configured ? '已配置（输入新值可替换）' : '未配置';
  if (token) token.placeholder = configured ? '输入新 Token 以替换当前值' : '输入 Refresh Token';
  setBadge('#connection-status', configured ? '已配置，待验证' : '未配置', configured ? 'warning' : 'neutral');
  setBadge('#api-status', configured ? '已配置，待验证' : '未配置', configured ? 'warning' : 'neutral');
  setText('#api-value', configured ? '待验证' : '未配置');
  setText('#api-detail', configured ? '请点击测试连接验证 Token' : '请先配置 Refresh Token');

  const toolEnabled = Boolean(settings.enable_natural_language_tool);
  setBadge('#tool-status', toolEnabled ? '已启用' : '已关闭', toolEnabled ? 'success' : 'neutral');
  setText('#tool-value', toolEnabled ? '已启用' : '已关闭');
  setText('#tool-detail', toolEnabled ? '支持自然语言触发' : '自然语言工具未启用');

  const filtersEnabled = Boolean(settings.filter_r18 || settings.filter_r18g);
  setBadge('#safety-status', filtersEnabled ? '过滤开启' : '过滤关闭', filtersEnabled ? 'success' : 'warning');
  setBadge('#safety-page-status', filtersEnabled ? '过滤开启' : '过滤关闭', filtersEnabled ? 'success' : 'warning');
  setText('#safety-value', filtersEnabled ? 'R-18 已过滤' : '未过滤');
  setText('#safety-detail', `R-18${settings.filter_r18 ? '' : ' 不'} / R-18G${settings.filter_r18g ? '' : ' 不'}过滤`);
  setText('#group-safety-value', '未接入');
  setText('#safety-hero-title', filtersEnabled ? '安全过滤已开启' : '安全过滤已关闭');
  setText('#safety-hero-detail', filtersEnabled ? '当前会过滤已标记的 R-18 / R-18G 作品。' : '当前不会自动过滤成人内容，请确认目标平台规则。');
  setText('#fallback-command-value', settings.enable_fallback_command ? '/pixiv' : '已关闭');

  setText('#last-saved', (settings.last_saved_at || settings.saved_at) ? `最后保存：${formatTimestamp(settings.last_saved_at || settings.saved_at)}` : '尚未保存');
}

function setSaveControlsEnabled(enabled) {
  document.querySelectorAll('.save-button, #save-overview').forEach(button => { button.disabled = !enabled; });
}

function buildSavePayload() {
  const payload = {
    ...loadedSettings,
    proxy: document.querySelector('#proxy')?.value ?? loadedSettings.proxy ?? '',
    timeout_seconds: Number(document.querySelector('#timeout')?.value ?? loadedSettings.timeout_seconds ?? 20),
    default_count: Number(document.querySelector('#count')?.value ?? loadedSettings.default_count ?? 5),
    max_file_size_mb: Number(document.querySelector('#max-size')?.value ?? loadedSettings.max_file_size_mb ?? 12),
  };
  const token = document.querySelector('#token')?.value.trim();
  if (token) payload.refresh_token = token;
  document.querySelectorAll('[data-config-key]').forEach(element => {
    payload[element.dataset.configKey] = element.checked;
  });
  return payload;
}

async function saveSettings(event) {
  const button = event?.currentTarget || document.querySelector('#save-overview');
  const originalText = button?.textContent || '保存设置';
  if (button) {
    button.disabled = true;
    button.dataset.saving = 'true';
    button.setAttribute('data-saving', 'true');
    button.textContent = '正在保存…';
  }
  try {
    const result = await apiPost('settings/save', buildSavePayload());
    applySettings(result);
    notify(result.message || '设置已保存');
  } catch (error) {
    notify(`保存失败：${error.message}`, true);
  } finally {
    if (button) {
      button.disabled = false;
      button.dataset.saving = 'false';
      button.setAttribute('data-saving', 'false');
      button.textContent = originalText;
    }
  }
}

function renderActivities(activities) {
  const host = document.querySelector('#activity-list');
  if (!host) return;
  host.replaceChildren();
  if (!activities?.length) {
    const empty = document.createElement('div');
    empty.className = 'activity-item';
    empty.innerHTML = '<span class="activity-mark">i</span><div><strong></strong><p></p></div>';
    empty.querySelector('strong').textContent = '暂无活动记录';
    empty.querySelector('p').textContent = '完成连接测试或发送请求后，活动会显示在这里。';
    host.append(empty);
    return;
  }
  activities.slice().reverse().forEach(activity => {
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML = `<span class="activity-mark ${activity.kind || ''}">${activity.kind === 'success' ? '✓' : 'i'}</span><div><strong></strong><p></p></div><time></time>`;
    item.querySelector('strong').textContent = activity.title || '活动';
    item.querySelector('p').textContent = activity.detail || '';
    item.querySelector('time').textContent = formatTimestamp(activity.at);
    host.append(item);
  });
}

async function loadSettings() {
  const settings = await apiGet('settings');
  applySettings(settings);
}

async function loadStats() {
  try {
    const stats = await apiGet('stats');
    setText('#requests-today', stats.requests_today ?? '—');
    setText('#images-sent-today', `${stats.images_sent_today ?? '—'} 张`);
    setText('#api-last-check', formatTimestamp(stats.last_connection_test_at));
    if (stats.last_status === '连接成功') {
      setBadge('#api-status', '连接成功', 'success');
      setText('#api-value', 'Connected');
      setText('#api-detail', 'Refresh Token 验证通过');
    } else if (stats.last_status === '连接失败') {
      setBadge('#api-status', '连接失败', 'error');
      setText('#api-value', '连接失败');
      setText('#api-detail', '请检查 Token、代理或网络设置');
    }
    renderActivities(stats.activities);
  } catch (error) {
    notify(`读取运行状态失败：${error.message}`, true);
  }
}

function renderDiagnostics(result) {
  const checks = result.checks || [];
  setText('#diagnostic-title', result.ok ? '诊断通过' : '需要处理配置');
  setText('#diagnostic-time', `完成 ${checks.length} 项检查，${result.passed?.length || 0} 项通过`);
  setText('#diagnostic-score', `${result.passed?.length || 0} / ${result.total || checks.length}`);
  const host = document.querySelector('#diagnostic-checks');
  if (host) {
    host.replaceChildren();
    checks.forEach(check => {
      const row = document.createElement('div');
      row.className = 'check-row';
      const status = check.status || (check.ok ? 'pass' : 'fail');
      const mark = status === 'pass' ? '✓' : (status === 'fail' ? '!' : '·');
      row.innerHTML = `<span class="check-mark ${status === 'pass' ? 'success' : (status === 'fail' ? 'warning' : 'neutral')}"></span><div><b></b><small></small></div><span class="check-state ${status === 'pass' ? 'success-text' : (status === 'fail' ? 'warning-text' : '')}">${status === 'pass' ? '通过' : (status === 'fail' ? '失败' : '未执行')}</span>`;
      row.querySelector('.check-mark').textContent = mark;
      row.querySelector('b').textContent = check.key;
      row.querySelector('small').textContent = check.message;
      host.append(row);
    });
  }
  setText('#diagnostic-log', checks.map(check => `[${check.status === 'pass' ? 'PASS' : (check.status === 'fail' ? 'FAIL' : 'NOT_RUN')}] ${check.key} · ${check.message}`).join('\n') || '没有检查结果。');
}

links.forEach(link => link.addEventListener('click', event => { event.preventDefault(); showView(link.dataset.view); }));
window.addEventListener('hashchange', () => showView(location.hash.slice(1) || 'overview'));
document.querySelector('#help-button')?.addEventListener('click', () => showView('guide'));
setSaveControlsEnabled(false);
document.querySelectorAll('.save-button, #save-overview').forEach(button => button.addEventListener('click', saveSettings));
document.querySelector('#test-connection')?.addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = '验证中…';
  try {
    const result = await apiPost('connection/test', {});
    setBadge('#connection-status', result.ok ? '连接成功' : '连接失败', result.ok ? 'success' : 'error');
    notify(result.message || 'Pixiv 连接测试完成', !result.ok);
    await loadStats();
  } catch (error) {
    setBadge('#connection-status', '连接失败', 'error');
    notify(`连接失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = '测试连接';
  }
});
document.querySelector('#clear-token')?.addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  button.dataset.saving = 'true';
  button.setAttribute('data-saving', 'true');
  const originalText = button.textContent;
  button.textContent = '正在清除…';
  try {
    const result = await apiPost('settings/save', { ...loadedSettings, refresh_token: '', last_saved_at: undefined });
    applySettings(result);
    notify('Refresh Token 已清除，设置已保存');
  } catch (error) {
    notify(`清除失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.dataset.saving = 'false';
    button.setAttribute('data-saving', 'false');
    button.textContent = originalText;
  }
});
document.querySelector('#run-diagnostics')?.addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = '检查中…';
  try {
    const result = await apiPost('diagnostics/run', {});
    renderDiagnostics(result);
    notify(result.ok ? '诊断通过' : '诊断完成，请检查配置', !result.ok);
  } catch (error) {
    notify(`诊断失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = '运行诊断';
  }
});
document.querySelector('#refresh-activity')?.addEventListener('click', () => loadStats().then(() => notify('活动记录已刷新')));
document.querySelector('#copy-diagnostics')?.addEventListener('click', () => {
  const log = document.querySelector('#diagnostic-log')?.textContent || '';
  navigator.clipboard?.writeText(log).then(() => notify('已复制脱敏诊断摘要')).catch(() => notify(log));
});
document.querySelectorAll('.copy-prompt').forEach(button => button.addEventListener('click', async () => {
  try { await navigator.clipboard?.writeText(button.dataset.copy); notify(`已复制：${button.dataset.copy}`); }
  catch { notify(`示例：${button.dataset.copy}`); }
}));

(async () => {
  try {
    await bridge?.ready?.();
    await loadSettings();
    await loadStats();
  } catch (error) {
    notify(`Bridge 尚未就绪：${error.message}`, true);
  }
  showView(location.hash.slice(1) || 'overview');
})();
