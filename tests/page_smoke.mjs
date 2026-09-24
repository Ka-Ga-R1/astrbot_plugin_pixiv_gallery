/**
 * Offline management-page smoke: node tests/page_smoke.mjs
 * Requires development-only Playwright + its Chromium (local install or NODE_PATH).
 * No server, Pixiv account, CDN access, screenshots, or production dependency needed.
 */
import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const expect = require('playwright/test').expect.configure({ timeout: 1800 });
const origin = 'https://pixiv-pages.test';
const apiPrefix = '/api/plugin/astrbot_plugin_pixiv_gallery/';
const files = new Map(await Promise.all(['index.html', 'app.js', 'style.css'].map(async name => [
  `/pages/pixiv-gallery/${name}`,
  await readFile(new URL(`../pages/pixiv-gallery/${name}`, import.meta.url), 'utf8'),
])));
const publicSettings = {
  proxy: 'http://127.0.0.1:7890', timeout_seconds: 35, default_count: 4, max_count: 8,
  enable_natural_language_tool: true, enable_fallback_command: true,
  enable_artist_random: true, enable_illust_id_send: true,
  search_target: 'title_and_caption', send_all_pages: true,
  show_work_metadata: true, show_pixiv_link: true,
  filter_r18: true, filter_r18g: true, reject_when_safety_check_failed: true,
  allow_private_r18: false, allow_group_r18: false,
  cache_ttl_minutes: 45, max_file_size_mb: 16, download_concurrency: 4, cooldown_seconds: 17,
  refresh_token_configured: true, last_saved_at: null,
};
const diagnosticResult = {
  ok: false,
  actual_message_delivery: 'not_run',
  checks: [
    { key: 'pixiv_api', status: 'pass', ok: true, message: 'Pixiv API 探测通过' },
    { key: 'proxy', status: 'fail', ok: false, message: '代理连接失败' },
    { key: 'image_download', status: 'not_run', ok: false, message: '未下载测试图片' },
    { key: 'message_chain', status: 'pass', ok: true, message: '消息链构造检查通过' },
  ],
  passed: ['pixiv_api', 'message_chain'],
  tested_at: '2026-09-24T06:30:00+00:00',
};
let browser;
before(async () => { browser = await chromium.launch({ headless: true }); });
after(async () => { await browser?.close(); });

async function openPage(t, options = {}) {
  const state = {
    settings: { ...publicSettings, ...options.settings },
    stats: {
      requests_today: 7, images_sent_today: 9, last_status: '未运行', activities: [],
      last_saved_at: null, last_connection_test_at: null,
      cache_entries: 12, cache_hits: 8, cache_misses: 4, date: '2026-09-24',
      ...options.stats,
    },
    diagnostics: structuredClone(diagnosticResult),
    calls: [], unexpected: [], ...options,
  };
  // Options above may specify partial settings/stats; retain the complete contract.
  state.settings = { ...publicSettings, ...options.settings };
  state.stats = {
    requests_today: 7, images_sent_today: 9, last_status: '未运行', activities: [],
    last_saved_at: null, last_connection_test_at: null,
    cache_entries: 12, cache_hits: 8, cache_misses: 4, date: '2026-09-24', ...options.stats,
  };
  const context = await browser.newContext({ locale: 'zh-CN', timezoneId: 'Asia/Shanghai' });
  const page = await context.newPage();
  page.setDefaultTimeout(1800);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(async () => {
    await context.close();
    assert.deepEqual(errors, [], 'No uncaught page errors');
    assert.deepEqual(state.unexpected, [], 'No unexpected network or Bridge routes');
  });
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) {
      // External styles/fonts are deliberately not fetched. The real local CSS is used.
      if (!['cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)) {
        state.unexpected.push(request.url());
      }
      return route.fulfill({ contentType: 'text/css', body: '' });
    }
    if (files.has(url.pathname)) {
      const type = url.pathname.endsWith('.js') ? 'text/javascript' : url.pathname.endsWith('.css') ? 'text/css' : 'text/html';
      return route.fulfill({ contentType: type, body: files.get(url.pathname) });
    }
    const endpoint = url.pathname.slice(apiPrefix.length);
    const key = `${request.method()} ${endpoint}`;
    if (!url.pathname.startsWith(apiPrefix) || ![
      'GET settings', 'GET stats', 'POST settings/save', 'POST cache/clear',
      'POST diagnostics/run', 'POST connection/test',
    ].includes(key)) {
      state.unexpected.push(request.url());
      return route.fulfill({ status: 404, body: 'Unexpected route' });
    }
    const body = request.postDataJSON();
    state.calls.push({ key, body });
    const respond = (value, status = 200) => route.fulfill({ status, json: value });
    const failureName = {
      'GET settings': 'settingsFailure', 'GET stats': 'statsFailure',
      'POST settings/save': 'saveFailure', 'POST cache/clear': 'cacheFailure',
      'POST diagnostics/run': 'diagnosticsFailure', 'POST connection/test': 'connectionFailure',
    }[key];
    if (state[failureName]) return respond(state[failureName].body, state[failureName].status);
    if (key === 'GET settings') return respond({ ...state.settings, last_connection_test_at: state.stats.last_connection_test_at });
    if (key === 'GET stats') return respond(state.stats);
    if (key === 'POST settings/save') {
      if (state.saveGate) await state.saveGate;
      const { refresh_token, ...fields } = body;
      Object.assign(state.settings, fields);
      delete state.settings.refresh_token;
      if (refresh_token !== undefined) state.settings.refresh_token_configured = Boolean(refresh_token);
      state.settings.last_saved_at = '2026-09-24T07:00:00+00:00';
      state.stats.last_saved_at = state.settings.last_saved_at;
      state.stats.last_status = '配置已更新，等待验证';
      state.stats.cache_entries = 0;
      return respond({ ...state.settings, saved: true, message: '设置已保存', saved_at: state.settings.last_saved_at });
    }
    if (key === 'POST cache/clear') {
      if (state.cacheGate) await state.cacheGate;
      const removed = state.stats.cache_entries;
      state.stats.cache_entries = 0;
      return respond({ cleared: true, removed_entries: removed, message: '元数据缓存已清空' });
    }
    if (key === 'POST diagnostics/run') {
      if (state.diagnosticsGate) await state.diagnosticsGate;
      return respond(state.diagnostics);
    }
    if (state.connectionGate) await state.connectionGate;
    state.stats.last_status = '连接成功';
    state.stats.last_connection_test_at = '2026-09-24T06:15:00+00:00';
    return respond({ ok: true, message: 'Pixiv 连接测试通过', tested_at: state.stats.last_connection_test_at });
  });
  if (options.bridge !== false) {
    await page.addInitScript(({ prefix }) => {
      async function request(method, endpoint, body) {
        const response = await fetch(`${prefix}${endpoint}`, {
          method, headers: { 'Content-Type': 'application/json' },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.message || `HTTP ${response.status}`);
        return result;
      }
      window.AstrBotPluginPage = {
        ready: async () => {},
        apiGet: endpoint => request('GET', endpoint),
        apiPost: (endpoint, body) => request('POST', endpoint, body),
      };
    }, { prefix: apiPrefix });
  }
  await page.goto(`${origin}/pages/pixiv-gallery/index.html#${options.view || 'overview'}`);
  if (!options.settingsFailure && options.bridge !== false) {
    await expect(page.locator('#save-overview')).toBeEnabled();
  }
  return { page, state };
}

const visit = (page, name) => page.locator(`#admin-nav [data-view="${name}"]`).click();
const control = (page, name) => page.locator(`[data-setting="${name}"]`);
const saves = state => state.calls.filter(call => call.key === 'POST settings/save');
const failure = (message, status = 502) => ({ status, body: { status: 'error', message } });

async function save(page, view = 'overview') {
  await page.locator(view === 'overview' ? '#save-overview' : `#view-${view} .save-button`).click();
  await expect(page.locator('#toast')).toContainText('设置已保存');
  await expect(page.locator('#save-overview')).toBeEnabled();
}

test('all settings hydrate and save typed values while preserving existing options', async t => {
  const { page, state } = await openPage(t);
  for (const [name, value] of Object.entries(publicSettings)) {
    if (name === 'refresh_token_configured' || name === 'last_saved_at') continue;
    if (typeof value === 'boolean') await expect(control(page, name)).toBeChecked({ checked: value });
    else await expect(control(page, name)).toHaveValue(String(value));
  }
  await visit(page, 'cache');
  await control(page, 'cache_ttl_minutes').fill('60');
  await control(page, 'cooldown_seconds').fill('0');
  await control(page, 'download_concurrency').fill('5');
  await control(page, 'max_file_size_mb').fill('24');
  await visit(page, 'chat');
  await control(page, 'default_count').fill('6');
  await control(page, 'max_count').fill('9');
  await control(page, 'search_target').selectOption('exact_match_for_tags');
  await control(page, 'send_all_pages').uncheck();
  await control(page, 'show_pixiv_link').uncheck();
  await control(page, 'show_work_metadata').uncheck();
  await visit(page, 'safety');
  await control(page, 'reject_when_safety_check_failed').uncheck();
  await control(page, 'allow_private_r18').check();
  await control(page, 'allow_group_r18').check();
  await save(page, 'safety');
  assert.deepEqual(saves(state).at(-1).body, {
    proxy: 'http://127.0.0.1:7890', timeout_seconds: 35, default_count: 6, max_count: 9,
    enable_natural_language_tool: true, enable_fallback_command: true,
    enable_artist_random: true, enable_illust_id_send: true,
    search_target: 'exact_match_for_tags', send_all_pages: false,
    show_work_metadata: false, show_pixiv_link: false,
    filter_r18: true, filter_r18g: true, reject_when_safety_check_failed: false,
    allow_private_r18: true, allow_group_r18: true,
    cache_ttl_minutes: 60, max_file_size_mb: 24, download_concurrency: 5, cooldown_seconds: 0,
  });
  await expect(page.locator('#last-saved')).toContainText('2026');
});

test('token readback is ignored; blank preserves, new value replaces, explicit clear deletes only the token', async t => {
  const { page, state } = await openPage(t, { settings: { refresh_token: 'readback-secret-must-not-be-reused' } });
  await expect(page.locator('#token')).toHaveValue('');
  await save(page);
  assert.equal(Object.hasOwn(saves(state).at(-1).body, 'refresh_token'), false);
  assert.equal(JSON.stringify(saves(state)).includes('readback-secret'), false);
  await visit(page, 'connection');
  await page.locator('#token').fill('  replacement-test-token  ');
  await save(page, 'connection');
  assert.equal(saves(state).at(-1).body.refresh_token, 'replacement-test-token');
  await expect(page.locator('#token')).toHaveValue('');
  await save(page, 'connection');
  assert.equal(Object.hasOwn(saves(state).at(-1).body, 'refresh_token'), false);
  await page.locator('#clear-token').click();
  await expect(page.locator('#toast')).toContainText('Refresh Token 已清除');
  assert.deepEqual(saves(state).at(-1).body, { refresh_token: '' });
  await expect(page.locator('#token-configured')).toHaveText('未配置');
  await expect(page.locator('#proxy')).toHaveValue('http://127.0.0.1:7890');
  await expect(page.locator('body')).not.toContainText('replacement-test-token');
});

test('candidate count stays independent of the total page cap and rejects out-of-range totals', async t => {
  const { page, state } = await openPage(t);
  await visit(page, 'chat');
  await control(page, 'max_count').fill('2');
  await control(page, 'default_count').fill('6');
  await save(page, 'chat');
  assert.equal(saves(state).at(-1).body.default_count, 6);
  assert.equal(saves(state).at(-1).body.max_count, 2);
  await expect(control(page, 'default_count')).toHaveValue('6');
  await expect(control(page, 'default_count')).toHaveAttribute('max', '10');
  await control(page, 'max_count').fill('21');
  await page.locator('#view-chat .save-button').click();
  await expect(page.locator('#toast .error')).toBeVisible();
  assert.equal(saves(state).length, 1);
  await expect(control(page, 'max_count')).toBeFocused();
});

test('invalid numeric edits never become zero, NaN or out-of-range save payloads', async t => {
  const { page, state } = await openPage(t);
  for (const [view, name, bad, good] of [
    ['cache', 'cache_ttl_minutes', '0', '45'], ['cache', 'download_concurrency', '6', '4'],
    ['cache', 'cooldown_seconds', '-1', '17'], ['cache', 'max_file_size_mb', '1.5', '16'],
    ['connection', 'timeout_seconds', '', '35'],
  ]) {
    await visit(page, view);
    await control(page, name).fill(bad);
    await page.locator(`#view-${view} .save-button`).click();
    await expect(page.locator('#toast .error')).toBeVisible();
    assert.equal(saves(state).length, 0, `${name} must not be saved`);
    await control(page, name).fill(good);
  }
});

test('one pending save locks every save/clear button and restores them after completion', async t => {
  const { page, state } = await openPage(t);
  let release;
  state.saveGate = new Promise(resolve => { release = resolve; });
  t.after(() => release());
  await page.locator('#save-overview').click();
  await expect(page.locator('#save-overview')).toHaveAttribute('data-saving', 'true');
  for (const button of await page.locator('.save-button, #save-overview, #clear-token').all()) {
    await expect(button).toBeDisabled();
  }
  await page.locator('#view-safety .save-button').evaluate(button => button.click());
  assert.equal(saves(state).length, 1);
  release();
  await expect(page.locator('#toast')).toContainText('设置已保存');
  for (const button of await page.locator('.save-button, #save-overview, #clear-token').all()) {
    await expect(button).toBeEnabled();
  }
});

for (const status of [200, 500]) {
  test(`save failure (${status}) preserves edits, is text-safe and never reports success`, async t => {
    const { page, state } = await openPage(t);
    await visit(page, 'connection');
    state.saveFailure = failure('mock save failed <img src=x onerror=alert(1)>', status);
    await page.locator('#token').fill('keep-this-draft');
    await page.locator('#view-connection .save-button').click();
    await expect(page.locator('#toast .error')).toContainText('mock save failed <img');
    await expect(page.locator('#toast img')).toHaveCount(0);
    await expect(page.locator('#token')).toHaveValue('keep-this-draft');
    await expect(page.locator('#last-saved')).toHaveText('尚未保存');
    await expect(page.locator('#clear-token')).toBeEnabled();
  });
}

test('failed settings read disables save and token clearing rather than saving defaults', async t => {
  const { page, state } = await openPage(t, { settingsFailure: failure('mock settings unavailable', 200) });
  await expect(page.locator('#toast .error')).toContainText('mock settings unavailable');
  for (const button of await page.locator('.save-button, #save-overview, #clear-token').all()) {
    await expect(button).toBeDisabled();
  }
  assert.equal(saves(state).length, 0);
  await expect(page.locator('#runtime-status')).not.toContainText('已连接');
});

test('a standalone page without Bridge stays visibly unavailable and cannot save', async t => {
  const { page } = await openPage(t, { bridge: false });
  await expect(page.locator('#toast .error')).toContainText('Bridge');
  await expect(page.locator('#save-overview')).toBeDisabled();
  await expect(page.locator('#clear-token')).toBeDisabled();
  await expect(page.locator('#runtime-status')).toContainText('未连接');
});

test('cache stats and clear use real response counts and refresh the current metadata state', async t => {
  const { page, state } = await openPage(t);
  await visit(page, 'cache');
  await expect(page.locator('#cache-entries')).toHaveText('12');
  await expect(page.locator('#cache-hits')).toHaveText('8');
  await expect(page.locator('#cache-misses')).toHaveText('4');
  await expect(page.locator('#cooldown-value')).toHaveText('17 秒');
  let release;
  state.cacheGate = new Promise(resolve => { release = resolve; });
  t.after(() => release());
  await page.locator('#clear-cache').click();
  await expect(page.locator('#clear-cache')).toBeDisabled();
  release();
  await expect(page.locator('#toast')).toContainText('12');
  await expect(page.locator('#toast')).not.toContainText('文件');
  await expect(page.locator('#cache-entries')).toHaveText('0');
  await expect(page.locator('#clear-cache')).toBeEnabled();
  assert.equal(state.calls.filter(call => call.key === 'POST cache/clear').length, 1);
  assert.deepEqual(state.calls.find(call => call.key === 'POST cache/clear').body, {});
  state.cacheFailure = failure('mock cache clear failed');
  state.stats.cache_entries = 3;
  await visit(page, 'overview');
  await visit(page, 'cache');
  await expect(page.locator('#cache-entries')).toHaveText('3');
  await page.locator('#clear-cache').click();
  await expect(page.locator('#toast .error')).toContainText('mock cache clear failed');
  await expect(page.locator('#cache-entries')).toHaveText('3');
});

test('stats date rolls over and failed refresh clears stale success instead of toasting refreshed', async t => {
  const { page, state } = await openPage(t, { stats: { last_status: '连接成功', last_connection_test_at: '2026-09-24T06:00:00Z' } });
  await expect(page.locator('#stats-date')).toContainText('2026-09-24');
  state.stats.date = '2026-09-25';
  state.stats.requests_today = 0;
  state.stats.images_sent_today = 0;
  await page.locator('#refresh-activity').click();
  await expect(page.locator('#stats-date')).toContainText('2026-09-25');
  await expect(page.locator('#requests-today')).toHaveText('0');
  state.statsFailure = failure('mock stats unavailable');
  await page.locator('#refresh-activity').click();
  await expect(page.locator('#toast .error')).toContainText('mock stats unavailable');
  await expect(page.locator('#toast')).not.toContainText('已刷新');
  await expect(page.locator('#cache-entries')).toHaveText('—');
  await expect(page.locator('#requests-today')).toHaveText('—');
  await expect(page.locator('#api-status')).not.toHaveClass(/success/);
});

test('safety summaries distinguish each global filter and never let scope permission override it', async t => {
  const { page } = await openPage(t, {
    settings: { filter_r18: false, filter_r18g: true, allow_group_r18: true, allow_private_r18: true, enable_natural_language_tool: false },
  });
  await expect(page.locator('#safety-value')).not.toHaveText('R-18 已过滤');
  await expect(page.locator('#group-safety-value')).toContainText('R-18');
  await expect(page.locator('#group-safety-value')).toContainText('R-18G 过滤');
  await expect(page.locator('#tool-value')).toHaveText('已关闭');
  await visit(page, 'safety');
  await expect(page.locator('#view-safety')).toContainText('全局过滤');
  await expect(page.locator('#view-safety')).toContainText('安全信息未知');
  await control(page, 'filter_r18').check();
  await save(page, 'safety');
  await expect(page.locator('#group-safety-value')).toContainText('全局过滤');
});

test('diagnostics render pass/fail/not_run, server time and message-chain-only scope', async t => {
  const { page, state } = await openPage(t);
  await visit(page, 'diagnostics');
  await page.locator('#run-diagnostics').click();
  await expect(page.locator('#diagnostic-score')).toHaveText('2 / 4');
  await expect(page.locator('#diagnostic-time')).toContainText('2026');
  await expect(page.locator('#diagnostic-checks .check-state')).toHaveText(['通过', '失败', '未执行', '通过']);
  await expect(page.locator('#diagnostic-log')).toContainText('[NOT_RUN] image_download');
  await expect(page.locator('#diagnostic-scope-note')).toContainText('不代表聊天平台实际送达');
  state.diagnostics = {
    ok: true, actual_message_delivery: 'not_run', passed: ['pixiv_api', 'proxy', 'image_download', 'message_chain'],
    tested_at: '2026-09-24T07:15:00Z',
    checks: diagnosticResult.checks.map(check => ({ ...check, status: 'pass', ok: true, message: '探测通过' })),
  };
  await page.locator('#run-diagnostics').click();
  await expect(page.locator('#diagnostic-score')).toHaveText('4 / 4');
  await expect(page.locator('#diagnostic-scope-note')).toContainText('不代表聊天平台实际送达');
  state.diagnosticsFailure = failure('mock diagnostics failed');
  await page.locator('#run-diagnostics').click();
  await expect(page.locator('#toast .error')).toContainText('mock diagnostics failed');
  await expect(page.locator('#diagnostic-score')).toHaveText('—');
  await expect(page.locator('#diagnostic-title')).toContainText('失败');
  await expect(page.locator('#diagnostic-checks .success')).toHaveCount(0);
});

test('connection checks use saved credentials and clear old success on failure', async t => {
  const { page, state } = await openPage(t);
  await visit(page, 'connection');
  await page.locator('#token').fill('unsaved-draft-token');
  await page.locator('#test-connection').click();
  await expect(page.locator('#connection-status')).toContainText('连接成功');
  assert.deepEqual(state.calls.find(call => call.key === 'POST connection/test').body, {});
  await expect(page.locator('#token')).toHaveValue('unsaved-draft-token');
  state.connectionFailure = failure('mock connection failed');
  await page.locator('#test-connection').click();
  await expect(page.locator('#toast .error')).toContainText('mock connection failed');
  await expect(page.locator('#api-status')).not.toHaveClass(/success/);
  await expect(page.locator('#connection-status')).not.toHaveClass(/success/);
});


test('backend candidate limit remains 10 while max_count permits 20 total image pages', async t => {
  const { page, state } = await openPage(t);
  await visit(page, 'chat');
  await control(page, 'max_count').fill('20');
  await control(page, 'default_count').fill('11');
  await save(page, 'chat');
  assert.equal(saves(state).at(-1).body.default_count, 10);
  assert.equal(saves(state).at(-1).body.max_count, 20);
  await expect(control(page, 'default_count')).toHaveAttribute('max', '10');
});

for (const lastStatus of ['已发送 3 张', '请求失败', '内容安全拦截', '配置已更新，等待验证']) {
  test(`request status "${lastStatus}" does not prove authenticated connectivity`, async t => {
    const { page } = await openPage(t, {
      stats: { last_status: lastStatus, last_connection_test_at: '2026-09-24T06:00:00Z' },
    });
    await expect(page.locator('#requests-today')).toHaveText('7');
    await expect(page.locator('#api-status')).not.toHaveClass(/success/);
    await expect(page.locator('#connection-status')).not.toHaveClass(/success/);
    await expect(page.locator('#api-value')).toHaveText('待验证');
  });
}

test('the diagnostic summary explicitly records actual_message_delivery as not_run', async t => {
  const { page } = await openPage(t);
  await visit(page, 'diagnostics');
  await page.locator('#run-diagnostics').click();
  await expect(page.locator('#diagnostic-log')).toContainText('[NOT_RUN] actual_message_delivery');
  await expect(page.locator('#diagnostic-scope-note')).toContainText('不代表聊天平台实际送达');
});

test('saving new settings invalidates a previous diagnostic report', async t => {
  const { page } = await openPage(t);
  await visit(page, 'diagnostics');
  await page.locator('#run-diagnostics').click();
  await expect(page.locator('#diagnostic-score')).toHaveText('2 / 4');
  await visit(page, 'connection');
  await page.locator('#proxy').fill('http://127.0.0.1:9000');
  await save(page, 'connection');
  await expect(page.locator('#diagnostic-score')).toHaveText('—');
  await expect(page.locator('#diagnostic-title')).toContainText('配置已更新');
});

for (const action of ['diagnostics', 'connection']) {
  test(`a late ${action} result cannot validate newly saved settings`, async t => {
    const { page, state } = await openPage(t);
    let release;
    state[`${action}Gate`] = new Promise(resolve => { release = resolve; });
    t.after(() => release());
    await visit(page, action);
    await page.locator(action === 'diagnostics' ? '#run-diagnostics' : '#test-connection').click();
    await visit(page, 'cache');
    await control(page, 'cache_ttl_minutes').fill('61');
    await save(page, 'cache');
    release();
    await expect(page.locator(action === 'diagnostics' ? '#run-diagnostics' : '#test-connection')).toBeEnabled();
    await expect(page.locator('#api-status')).not.toHaveClass(/success/);
    await expect(page.locator('#diagnostic-score')).toHaveText('—');
  });
}

test('an old connection timestamp cannot validate settings saved more recently', async t => {
  const { page } = await openPage(t, {
    settings: { last_saved_at: '2026-09-24T07:00:00Z' },
    stats: { last_status: '连接成功', last_connection_test_at: '2026-09-24T06:00:00Z', last_saved_at: '2026-09-24T07:00:00Z' },
  });
  await expect(page.locator('#requests-today')).toHaveText('7');
  await expect(page.locator('#api-status')).not.toHaveClass(/success/);
  await expect(page.locator('#connection-status')).not.toHaveClass(/success/);
});


test('saving cache settings reloads stats instead of retaining pre-save entry counts', async t => {
  const { page } = await openPage(t);
  await visit(page, 'cache');
  await expect(page.locator('#cache-entries')).toHaveText('12');
  await control(page, 'cache_ttl_minutes').fill('46');
  await save(page, 'cache');
  await expect(page.locator('#cache-entries')).toHaveText('0');
});
