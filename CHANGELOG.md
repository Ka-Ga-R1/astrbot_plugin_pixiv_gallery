# Changelog

## 0.1.3 — 2026-09-24

- Japanese Pixiv tag queries try one SFW Lolicon candidate first; candidate discovery is not restricted by the configured bookmark tier. Pixiv fallback searches still force the selected `users入り` tag.
- Fetch Lolicon candidates and original images from Pixiv, preserving Pixiv safety checks and Pixiv-hosted original URLs.
- Add configurable bookmark thresholds and use `https://www.pixiv.net/` as the original-image Referer.
- Improve explicit Pixiv artist/illustration ID diagnostics and add ID, fallback, safety, and Pages regressions.

## 0.1.2 — 2026-09-24

- Fix Pixiv OAuth signing, token refresh/expiry handling, artist illustration endpoint, bounded pagination, and sanitized API failures.
- Return explicit text results from the natural-language tool and await image delivery before cleaning temporary files.
- Enforce content-safety defaults on searches, IDs, and cached metadata; reject unknown safety metadata by default.
- Apply bounded metadata caching, cooldowns, global download concurrency, image size/host validation, and accurate daily send statistics.
- Connect Pages settings, cache controls, connection tests, and real diagnostics; never return saved refresh tokens.
- Improve Chinese/English ID and count parsing, and document candidate count versus total image-page limits.
- Add regression, integration, package-contract, and Pages smoke tests; keep test dependencies separate from runtime dependencies.
