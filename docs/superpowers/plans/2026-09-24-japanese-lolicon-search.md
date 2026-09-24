# Japanese Pixiv Tag Search and Lolicon Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Improve Japanese Pixiv tag discovery with a Lolicon candidate-first path, configurable bookmark tiers, reliable original-image delivery, and diagnosable Pixiv ID requests.

**Architecture:** Keep orchestration in `YumeiroPlugin`, Pixiv response normalization in `PixivClient`, and image safety in `ImageDownloader`. Add a small injectable Lolicon API client; its records identify candidates only, while every delivered work and original image comes from Pixiv. Keep current content policy as the final authority.

**Tech Stack:** Python 3.10+, existing `httpx` dependency, AstrBot Pages, pytest, Node/Playwright smoke tests.

**Spec:** `docs/superpowers/specs/2026-09-24-japanese-lolicon-search.md`

## Global Constraints
- No secrets or raw external response bodies in logs or user-visible errors.
- Lolicon is SFW-only (`r18=0`) and its image URLs are never downloaded.
- Current Pixiv content-safety filters and HTTPS/host/redirect/size/image checks remain enabled.
- ID requests bypass keyword-only Lolicon/tag behavior.
- Bookmark threshold defaults to `100users入り` and has only the seven approved values; it applies to Pixiv keyword fallback, not Lolicon candidates.
- Image requests use Pixiv original URLs and `Referer: https://www.pixiv.net/`.

---

### Task 1: Pixiv IDs, original image requests, and safe diagnostics

**Files:** `main.py`, `pixiv_gallery/pixiv_client.py`, `pixiv_gallery/downloader.py`; related client/downloader/tool tests.

- [x] Add tests for the supplied artist and illustration IDs: assert exact Pixiv endpoint and parameter names, response ID/UID normalization, and `artist_id`/`illust_id` forwarding from the LLM tool.
- [x] Add an image transport test asserting the original Pixiv image URL is requested with `Referer: https://www.pixiv.net/`.
- [x] Run focused tests and confirm they fail for the expected missing assertions/behavior.
- [x] Implement minimal safe diagnostic categorization (known Pixiv HTTP status or network category, no raw exception or token).
- [x] Run focused tests and verify existing safety/download tests still pass.

### Task 2: Lolicon candidate-first search and Pixiv fallback

**Files:** create `pixiv_gallery/lolicon_client.py`; modify `main.py`, possibly `pixiv_gallery/service.py`; tests for Lolicon and tool orchestration.

- [x] Add injectable-client tests for request parameters (`r18=0`, one candidate, repeated Japanese `tag` parameters, no bookmark-tier constraint), empty results, malformed records, HTTP/network errors, and response redaction.
- [x] Add tool-flow tests proving candidate `uid`/`pid` is fetched from Pixiv, Lolicon image URLs are ignored, Pixiv safety is applied, and fallback receives the same Japanese tags.
- [x] Run focused tests and observe the expected failures.
- [x] Implement the bounded Lolicon client and keyword orchestration; explicit IDs skip it.
- [x] Require safe, usable Pixiv records before delivery; fall back to direct Pixiv tag search after empty/error/ineligible candidates.
- [x] Update LLM tool help to request concise Japanese Pixiv tag terms, with examples.

### Task 3: Configurable mandatory bookmark tier and final regression

**Files:** `pixiv_gallery/config.py`, `_conf_schema.json`, `pages/pixiv-gallery/index.html`, page contract/browser tests, README/CHANGELOG, and any search tests.

- [x] Add tests for all seven values, invalid-config normalization, default tier, settings read/save, Page control options, unrestricted Lolicon candidates, and mandatory tag propagation to Pixiv fallback.
- [x] Run tests and observe failures.
- [x] Implement the setting in config and Page as a single select control; append it only to keyword-search paths.
- [x] Document Japanese tag expectations, candidate-first flow, fallback, bookmark-tier behavior, Pixiv original image Referer, and ID toggle guidance.
- [x] Run full Python tests, ruff, formatting, compileall, JavaScript syntax, Page smoke, and `git diff --check`.
- [x] Review the complete diff for secret safety, scope compliance, and user-provided ID regressions.
