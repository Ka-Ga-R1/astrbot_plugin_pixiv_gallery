# Yumeiro Pixiv Plugin Implementation Plan

**Goal:** Build an AstrBot plugin named `astrbot_plugin_pixiv_gallery` with natural-language Pixiv illustration search, optional artist-ID random selection, optional illustration-ID sending, persistent configuration through Plugin Pages, and a Yumeiro management console.

**Architecture:** The plugin uses AstrBot's `AstrBotConfig` plus `_conf_schema.json` for persistent settings. A small Pixiv client boundary handles token-authenticated API calls, while a service layer validates requests, applies safety/limits, downloads images, and formats AstrBot message chains. Plugin Pages call namespaced backend routes through the Bridge API and never access secrets directly.

**Tech Stack:** Python 3.10+, AstrBot Star API, aiohttp/httpx-compatible async HTTP, pytest, vanilla HTML/CSS/JS with daisyUI-compatible classes.

## Global Constraints

- Natural-language Tool is the primary trigger; `/pixiv` is a fallback command.
- Default search target is Pixiv partial tag matching.
- R-18 and R-18G filtering is enabled by default and cannot be bypassed by ID requests.
- Artist-ID random selection and illustration-ID sending are independently configurable and disabled by default.
- Refresh Token is never returned to Pages or logs.
- Pages save requests must validate values server-side before calling `save_config()`.
- No real Pixiv credentials are used in tests.

### Task 1: Repository and plugin metadata

**Files:**
- Create: `metadata.yaml`, `_conf_schema.json`, `requirements.txt`, `README.md`, `.gitignore`, `main.py`
- Create: `pixiv_gallery/__init__.py`, `pixiv_gallery/models.py`, `pixiv_gallery/config.py`
- Test: `tests/test_config.py`

- [ ] Write failing tests for defaults, bounds, and secret redaction.
- [ ] Run `pytest tests/test_config.py -q` and verify failure.
- [ ] Implement configuration normalization and redacted public state.
- [ ] Run the focused tests and verify pass.
- [ ] Add AstrBot metadata and dependency files.

### Task 2: Pixiv client boundary

**Files:**
- Create: `pixiv_gallery/pixiv_client.py`
- Test: `tests/test_pixiv_client.py`

- [ ] Write failing tests for search target, user illustration lookup, detail lookup, token refresh, and request errors.
- [ ] Run focused tests and verify failure.
- [ ] Implement an injectable async transport boundary and Pixiv response normalization.
- [ ] Run focused tests and verify pass.

### Task 3: Search and request service

**Files:**
- Create: `pixiv_gallery/service.py`, `pixiv_gallery/safety.py`, `pixiv_gallery/downloader.py`
- Test: `tests/test_service.py`, `tests/test_safety.py`

- [ ] Write failing tests for tag search, artist random selection, illustration ID selection, count limits, safety filtering, and temp cleanup.
- [ ] Run focused tests and verify failure.
- [ ] Implement service orchestration and bounded random selection.
- [ ] Run focused tests and verify pass.

### Task 4: AstrBot triggers and message sending

**Files:**
- Modify: `main.py`
- Create: `pixiv_gallery/formatting.py`
- Test: `tests/test_formatting.py`

- [ ] Write failing tests for parsed request priority: illust ID > artist ID > keyword search.
- [ ] Run focused tests and verify failure.
- [ ] Implement `/pixiv` command and `@filter.llm_tool` with strict docstring schema.
- [ ] Build image/text message chains using AstrBot components.
- [ ] Run tests and static import checks.

### Task 5: Plugin Pages backend

**Files:**
- Modify: `main.py`
- Modify: `pages/pixiv-gallery/index.html`, `pages/pixiv-gallery/app.js`
- Create: `pages/pixiv-gallery/bridge.js`, `.astrbot-plugin/i18n/zh-CN.json`
- Test: `tests/test_pages_api.py`

- [ ] Write failing tests for redacted GET settings and validated POST updates.
- [ ] Run focused tests and verify failure.
- [ ] Register namespaced settings, connection test, cache clear, and diagnostics routes.
- [ ] Replace preview-only actions with `bridge.apiGet/apiPost` calls and loading/error states.
- [ ] Run focused tests and browser smoke test.

### Task 6: Documentation and packaging

**Files:**
- Modify: `README.md`, `metadata.yaml`
- Create: `LICENSE`

- [ ] Document Refresh Token setup, configuration, commands, natural-language examples, safety behavior, and ID features.
- [ ] Run package file audit excluding backups and `doc_cache`.
- [ ] Run full test suite and compile checks.

### Task 7: Review and GitHub publication

- [ ] Inspect the complete diff and run verification commands.
- [ ] Commit with a descriptive message.
- [ ] Configure or confirm a user-provided GitHub remote; do not invent a repository URL.
- [ ] Push the verified commit to the configured public repository.
