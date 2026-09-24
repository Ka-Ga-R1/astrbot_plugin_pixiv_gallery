const bridge = window.AstrBotPluginPage;
const panels = [...document.querySelectorAll('[data-view-panel]')];
const links = [...document.querySelectorAll('[data-view]')];
const settingControls = [...document.querySelectorAll('[data-setting]')];
let toastTimer;
let loadedSettings = {};
let settingsReady = false;
let saving = false;
let statsGeneration = 0;
let settingsGeneration = 0;

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

function showView(name, refresh = true) {
  const next = panels.some(panel => panel.dataset.viewPanel === name) ? name : 'overview';
  panels.forEach(panel => panel.classList.toggle('active', panel.dataset.viewPanel === next));
  document.querySelectorAll('.admin-nav-link').forEach(link => {
    const active = link.dataset.view === next;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  history.replaceState(null, '', `#${next}`);
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (refresh && settingsReady && ['overview', 'cache'].includes(next)) loadStats();
}

function checkedResponse(result) {
  if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error('接口未返回有效结果');
  if (result.status === 'error') throw new Error(result.message || '请求失败');
  return result;
}

async function apiGet(endpoint, params) {
  if (!bridge?.apiGet) throw new Error('当前页面尚未连接 AstrBot Bridge');
  return checkedResponse(await bridge.apiGet(endpoint, params));
}

async function apiPost(endpoint, body) {
  if (!bridge?.apiPost) throw new Error('当前页面尚未连接 AstrBot Bridge');
  return checkedResponse(await bridge.apiPost(endpoint, body));
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
  element.replaceChildren(document.createElement('i'), document.createTextNode(label));
}

function formatTimestamp(value) {
  if (!value) return '尚无记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' });
}

function setRuntimeStatus(label, state = 'neutral') {
  setText('#runtime-status', label);
  const dot = document.querySelector('#runtime-dot');
  if (dot) dot.className = `status-dot ${state}`;
}

function setReadiness(selector, title, detail, complete = false) {
  const element = document.querySelector(selector);
  if (!element) return;
  element.classList.toggle('done', complete);
  element.classList.toggle('pending', !complete);
  element.querySelector('span').textContent = complete ? '✓' : '·';
  element.querySelector('b').textContent = title;
  element.querySelector('small').textContent = detail;
}

function setConnectionState(label, state, detail) {
  setBadge('#connection-status', label, state);
  setBadge('#api-status', label, state);
  setText('#api-value', label === '已配置，待验证' ? '待验证' : label);
  setText('#api-detail', detail);
  setReadiness('#readiness-connection', label, detail, state === 'success');
}

function resetConnectionState() {
  const configured = loadedSettings.refresh_token_configured;
  setConnectionState(configured ? '已配置，待验证' : '未配置', configured ? 'warning' : 'neutral',
    configured ? '请点击测试连接验证已保存的配置' : '请先配置 Refresh Token');
}

function scopeSummary(settings, allowed) {
  if (!allowed) return '不允许成人内容';
  if (settings.filter_r18 && settings.filter_r18g) return '全局过滤（不允许）';
  return `R-18 ${settings.filter_r18 ? '过滤' : '允许'} · R-18G ${settings.filter_r18g ? '过滤' : '允许'}`;
}

function syncCountLimit() {
  const count = document.querySelector('#count');
  if (!count) return;
  count.max = '10';
  if (Number.isInteger(Number(count.value)) && Number(count.value) > 10) count.value = 10;
}

function applySettings(settings) {
  if (typeof settings.refresh_token_configured !== 'boolean') throw new Error('未读取到完整的公开设置');
  // Only declared settings may be retained/submitted. Never retain a token from readback.
  settingControls.forEach(element => {
    const key = element.dataset.setting;
    if (key === 'refresh_token' || settings[key] === undefined) return;
    loadedSettings[key] = settings[key];
    if (element.type === 'checkbox') element.checked = settings[key] === true;
    else element.value = settings[key];
  });
  loadedSettings.refresh_token_configured = settings.refresh_token_configured;
  syncCountLimit();
  settingsReady = true;
  setSaveControlsEnabled(!saving);

  const configured = settings.refresh_token_configured;
  const token = document.querySelector('#token');
  if (token) {
    token.value = '';
    token.placeholder = configured ? '输入新 Token 以替换当前值' : '输入 Refresh Token';
  }
  setText('#token-configured', configured ? '已配置（输入新值可替换）' : '未配置');
  resetConnectionState();
  setRuntimeStatus('管理接口已连接', 'success');
  setReadiness('#readiness-bridge', '管理接口已连接', '已读取公开配置，不包含 Token', true);

  const toolEnabled = loadedSettings.enable_natural_language_tool === true;
  for (const selector of ['#tool-status', '#chat-tool-status']) {
    setBadge(selector, toolEnabled ? '已启用' : '已关闭', toolEnabled ? 'success' : 'neutral');
  }
  setText('#tool-value', toolEnabled ? '已启用' : '已关闭');
  setText('#tool-detail', toolEnabled ? '配置已启用，实际触发需在聊天中验证' : '自然语言工具未启用');
  setReadiness('#readiness-tool', toolEnabled ? '工具配置已启用' : '工具配置已关闭', '实际触发需在聊天中验证');
  setText('#fallback-command-value', loadedSettings.enable_fallback_command ? '/pixiv' : '已关闭');

  const filtered = [loadedSettings.filter_r18 && 'R-18', loadedSettings.filter_r18g && 'R-18G'].filter(Boolean);
  const safetyState = filtered.length === 2 && loadedSettings.reject_when_safety_check_failed ? 'success' : 'warning';
  const safetyLabel = filtered.length === 2 ? '全局过滤开启' : filtered.length ? '部分过滤开启' : '全局过滤关闭';
  setBadge('#safety-status', safetyLabel, safetyState);
  setBadge('#safety-page-status', safetyLabel, safetyState);
  setText('#safety-value', filtered.length ? `${filtered.join(' / ')} 过滤` : '全局过滤关闭');
  setText('#safety-detail', `R-18 ${loadedSettings.filter_r18 ? '过滤' : '不过滤'} / R-18G ${loadedSettings.filter_r18g ? '过滤' : '不过滤'}`);
  setText('#group-safety-value', scopeSummary(loadedSettings, loadedSettings.allow_group_r18));
  setText('#safety-hero-title', safetyLabel);
  setText('#safety-hero-detail', `全局过滤优先；私聊：${scopeSummary(loadedSettings, loadedSettings.allow_private_r18)}；群聊：${scopeSummary(loadedSettings, loadedSettings.allow_group_r18)}。安全信息未知时${loadedSettings.reject_when_safety_check_failed ? '拒绝发送' : '允许继续（高风险）'}。`);
  setText('#cache-ttl-value', `${loadedSettings.cache_ttl_minutes} 分钟`);
  setText('#cooldown-value', loadedSettings.cooldown_seconds ? `${loadedSettings.cooldown_seconds} 秒` : '已关闭');
  setBadge('#cooldown-status', loadedSettings.cooldown_seconds ? '已配置' : '未启用', 'neutral');
  const savedAt = settings.saved_at || settings.last_saved_at;
  setText('#last-saved', savedAt ? `最后保存：${formatTimestamp(savedAt)}` : '尚未保存');
}

function setSaveControlsEnabled(enabled) {
  document.querySelectorAll('.save-button, #save-overview, #clear-token').forEach(button => { button.disabled = !enabled; });
  settingControls.forEach(element => { element.disabled = !enabled; });
  document.querySelectorAll('#test-connection, #run-diagnostics, #clear-cache, #refresh-activity').forEach(button => {
    button.disabled = !enabled || button.dataset.busy === 'true';
  });
}

function buildSavePayload() {
  syncCountLimit();
  const payload = {};
  settingControls.forEach(element => {
    const key = element.dataset.setting;
    if (key === 'refresh_token') {
      const token = element.value.trim();
      if (token) payload.refresh_token = token;
    } else if (element.type === 'checkbox') {
      payload[key] = element.checked;
    } else if (element.type === 'number') {
      const value = Number(element.value);
      if (!element.value.trim() || !Number.isInteger(value) || value < Number(element.min) || value > Number(element.max)) {
        showView(element.closest('[data-view-panel]').dataset.viewPanel);
        element.setAttribute('aria-invalid', 'true');
        element.focus();
        const label = document.querySelector(`label[for="${element.id}"]`)?.textContent || key;
        throw new Error(`${label}须为 ${element.min}–${element.max} 的整数`);
      }
      payload[key] = value;
    } else {
      payload[key] = element.value;
    }
  });
  return payload;
}

async function persistSettings(button, payload, clearToken = false) {
  if (!settingsReady || saving) return;
  const originalText = button.textContent;
  saving = true;
  setSaveControlsEnabled(false);
  button.dataset.saving = 'true';
  button.setAttribute('aria-busy', 'true');
  button.textContent = clearToken ? '正在清除…' : '正在保存…';
  try {
    const result = await apiPost('settings/save', payload);
    if (result.saved !== true) throw new Error(result.message || '服务器未确认保存');
    applySettings(result);
    settingsGeneration += 1;
    statsGeneration += 1;
    resetDiagnostics('配置已更新', '设置已更改，请重新运行诊断。');
    await loadStats();
    notify(clearToken ? 'Refresh Token 已清除，设置已保存' : (result.message || '设置已保存'));
  } catch (error) {
    notify(`${clearToken ? '清除' : '保存'}失败：${error.message}`, true);
  } finally {
    saving = false;
    button.dataset.saving = 'false';
    button.setAttribute('aria-busy', 'false');
    button.textContent = originalText;
    setSaveControlsEnabled(settingsReady);
  }
}

async function saveSettings(event) {
  if (!settingsReady || saving) return;
  try {
    const payload = buildSavePayload();
    await persistSettings(event.currentTarget, payload);
  } catch (error) {
    notify(`保存失败：${error.message}`, true);
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
    item.innerHTML = '<span class="activity-mark"></span><div><strong></strong><p></p></div><time></time>';
    const mark = item.querySelector('.activity-mark');
    if (['success', 'warning', 'error'].includes(activity.kind)) mark.classList.add(activity.kind);
    mark.textContent = activity.kind === 'success' ? '✓' : 'i';
    item.querySelector('strong').textContent = activity.title || '活动';
    item.querySelector('p').textContent = activity.detail || '';
    item.querySelector('time').textContent = formatTimestamp(activity.at);
    host.append(item);
  });
}

async function loadSettings() {
  applySettings(await apiGet('settings'));
}

async function loadStats() {
  const generation = ++statsGeneration;
  try {
    const stats = await apiGet('stats');
    if (generation !== statsGeneration) return false;
    setText('#requests-today', stats.requests_today ?? '—');
    setText('#images-sent-today', `${stats.images_sent_today ?? '—'} 张`);
    setText('#stats-date', stats.date || '日期未知');
    setBadge('#stats-status', '运行统计', 'neutral');
    setText('#api-last-check', formatTimestamp(stats.last_connection_test_at));
    const savedAt = Date.parse(stats.last_saved_at || loadedSettings.last_saved_at || '');
    const testedAt = Date.parse(stats.last_connection_test_at || '');
    if (stats.last_status === '连接成功' && Number.isFinite(testedAt) &&
        (!Number.isFinite(savedAt) || testedAt >= savedAt)) {
      setConnectionState('连接成功', 'success', '已保存配置的最近一次连接测试通过');
    } else if (stats.last_status === '连接失败') {
      setConnectionState('连接失败', 'error', '请检查 Token、代理或网络设置');
    } else {
      resetConnectionState();
    }
    setText('#cache-entries', stats.cache_entries ?? '—');
    setText('#cache-hits', stats.cache_hits ?? '—');
    setText('#cache-misses', stats.cache_misses ?? '—');
    setBadge('#cache-status', stats.cache_entries === undefined ? '状态未知' : '内存元数据', 'neutral');
    renderActivities(stats.activities);
    setRuntimeStatus('运行状态已读取', 'success');
    return true;
  } catch (error) {
    if (generation !== statsGeneration) return false;
    for (const selector of ['#requests-today', '#images-sent-today', '#cache-entries', '#cache-hits', '#cache-misses', '#api-last-check']) setText(selector, '—');
    setText('#stats-date', '日期未知');
    setBadge('#stats-status', '读取失败', 'error');
    setBadge('#cache-status', '状态未知', 'warning');
    setConnectionState('状态未知', 'neutral', '运行状态读取失败，请重新测试连接');
    setText('#activity-list', '活动记录读取失败，请重试。');
    setRuntimeStatus('状态读取失败', 'error');
    notify(`读取运行状态失败：${error.message}`, true);
    return false;
  }
}

function resetDiagnostics(title, message, state = 'neutral') {
  setText('#diagnostic-title', title);
  setText('#diagnostic-time', message);
  setText('#diagnostic-score', '—');
  setText('#diagnostic-checks', message);
  setText('#diagnostic-log', message);
  document.querySelector('.diagnostic-summary').dataset.state = state;
}

function renderDiagnostics(result) {
  const checks = Array.isArray(result.checks) ? result.checks : [];
  const passed = checks.filter(check => check.status === 'pass').length;
  const failed = checks.filter(check => check.status === 'fail').length;
  const notRun = checks.length - passed - failed;
  const allPassed = result.ok === true && checks.length > 0 && passed === checks.length;
  const title = allPassed ? '检查全部通过' : failed ? '检查发现问题' : notRun ? '部分检查未执行' : '未获得有效检查结果';
  setText('#diagnostic-title', title);
  setText('#diagnostic-time', `检测时间：${formatTimestamp(result.tested_at)} · ${passed} 项通过，${failed} 项失败，${notRun} 项未执行`);
  setText('#diagnostic-score', `${passed} / ${checks.length}`);
  document.querySelector('.diagnostic-summary').dataset.state = allPassed ? 'success' : failed ? 'error' : 'warning';
  const labels = { pixiv_api: 'Pixiv API', proxy: '网络 / 代理', image_download: '安全图片下载', message_chain: '消息链构造（非实际送达）' };
  const host = document.querySelector('#diagnostic-checks');
  host.replaceChildren();
  checks.forEach(check => {
    const status = ['pass', 'fail'].includes(check.status) ? check.status : 'not_run';
    const state = status === 'pass' ? 'success' : status === 'fail' ? 'warning' : 'neutral';
    const row = document.createElement('div');
    row.className = 'check-row';
    row.innerHTML = `<span class="check-mark ${state}"></span><div><b></b><small></small></div><span class="check-state ${state}-text"></span>`;
    row.querySelector('.check-mark').textContent = status === 'pass' ? '✓' : status === 'fail' ? '!' : '·';
    row.querySelector('b').textContent = labels[check.key] || check.key;
    row.querySelector('small').textContent = check.message || '';
    row.querySelector('.check-state').textContent = status === 'pass' ? '通过' : status === 'fail' ? '失败' : '未执行';
    host.append(row);
  });
  const lines = checks.map(check => `[${check.status === 'pass' ? 'PASS' : check.status === 'fail' ? 'FAIL' : 'NOT_RUN'}] ${check.key} · ${check.message || ''}`);
  if (result.actual_message_delivery === 'not_run') {
    lines.push('[NOT_RUN] actual_message_delivery · 没有聊天事件，未验证实际平台投递');
  }
  const scope = document.querySelector('#diagnostic-scope-note').textContent;
  setText('#diagnostic-log', [`检测时间：${formatTimestamp(result.tested_at)}`, ...lines, scope].join('\n'));
  return allPassed;
}

function startAction(button, text) {
  const originalText = button.textContent;
  button.disabled = true;
  button.dataset.busy = 'true';
  button.setAttribute('aria-busy', 'true');
  button.textContent = text;
  return () => {
    button.dataset.busy = 'false';
    button.setAttribute('aria-busy', 'false');
    button.textContent = originalText;
    button.disabled = !settingsReady || saving;
  };
}

links.forEach(link => link.addEventListener('click', event => { event.preventDefault(); showView(link.dataset.view); }));
window.addEventListener('hashchange', () => showView(location.hash.slice(1) || 'overview'));
document.querySelector('#help-button')?.addEventListener('click', () => showView('guide'));
setSaveControlsEnabled(false);
settingControls.forEach(element => element.addEventListener('input', () => element.removeAttribute('aria-invalid')));
document.querySelectorAll('.save-button, #save-overview').forEach(button => button.addEventListener('click', saveSettings));
document.querySelector('#clear-token')?.addEventListener('click', event => persistSettings(event.currentTarget, { refresh_token: '' }, true));
document.querySelector('#test-connection')?.addEventListener('click', async event => {
  const generation = settingsGeneration;
  const finish = startAction(event.currentTarget, '验证中…');
  setConnectionState('验证中…', 'neutral', '正在测试已保存的 Token 与网络配置');
  try {
    const result = await apiPost('connection/test', {});
    if (generation !== settingsGeneration) return;
    if (result.ok !== true) throw new Error(result.message || '连接测试未通过');
    setConnectionState('连接成功', 'success', result.message || '连接测试通过');
    setText('#api-last-check', formatTimestamp(result.tested_at));
    const refreshed = await loadStats();
    notify(`${result.message || 'Pixiv 连接测试通过'}${refreshed ? '' : '；运行状态读取失败'}`, !refreshed);
  } catch (error) {
    if (generation !== settingsGeneration) return;
    statsGeneration += 1;
    setConnectionState('连接失败', 'error', '请检查 Token、代理或网络设置');
    notify(`连接失败：${error.message}`, true);
  } finally {
    finish();
  }
});
document.querySelector('#clear-cache')?.addEventListener('click', async event => {
  const finish = startAction(event.currentTarget, '清理中…');
  statsGeneration += 1;
  try {
    const result = await apiPost('cache/clear', {});
    if (result.cleared !== true || !Number.isInteger(result.removed_entries) || result.removed_entries < 0) {
      throw new Error(result.message || '服务器未确认清理结果');
    }
    const refreshed = await loadStats();
    notify(`${result.message || '元数据缓存已清空'}（移除 ${result.removed_entries} 条元数据）${refreshed ? '' : '；运行状态读取失败'}`, !refreshed);
  } catch (error) {
    notify(`清理失败：${error.message}`, true);
  } finally {
    finish();
  }
});
document.querySelector('#run-diagnostics')?.addEventListener('click', async event => {
  const generation = settingsGeneration;
  const finish = startAction(event.currentTarget, '检查中…');
  resetDiagnostics('正在运行诊断', '等待本次检查结果。');
  try {
    const result = await apiPost('diagnostics/run', {});
    if (generation !== settingsGeneration) return;
    const allPassed = renderDiagnostics(result);
    notify(allPassed ? '检查全部通过；实际聊天送达仍需验证' : '诊断完成，请查看检查结果', !allPassed);
  } catch (error) {
    if (generation !== settingsGeneration) return;
    resetDiagnostics('诊断失败', `未获取本次检查结果：${error.message}`, 'error');
    notify(`诊断失败：${error.message}`, true);
  } finally {
    finish();
  }
});
document.querySelector('#refresh-activity')?.addEventListener('click', async event => {
  const finish = startAction(event.currentTarget, '刷新中…');
  try {
    if (await loadStats()) notify('活动记录已刷新');
  } finally {
    finish();
  }
});
document.querySelector('#copy-diagnostics')?.addEventListener('click', () => {
  const log = document.querySelector('#diagnostic-log')?.textContent || '';
  navigator.clipboard?.writeText(log).then(() => notify('已复制脱敏诊断摘要')).catch(() => notify(log));
});
document.querySelectorAll('.copy-prompt').forEach(button => button.addEventListener('click', async () => {
  try { await navigator.clipboard?.writeText(button.dataset.copy); notify(`已复制：${button.dataset.copy}`); }
  catch { notify(`示例：${button.dataset.copy}`); }
}));

showView(location.hash.slice(1) || 'overview', false);
(async () => {
  try {
    await bridge?.ready?.();
    await loadSettings();
    await loadStats();
  } catch (error) {
    settingsReady = false;
    setSaveControlsEnabled(false);
    setRuntimeStatus('Bridge 未连接', 'error');
    setReadiness('#readiness-bridge', '管理接口读取失败', '请检查 Bridge 后重新加载页面');
    notify(`Bridge 尚未就绪：${error.message}`, true);
  }
})();
