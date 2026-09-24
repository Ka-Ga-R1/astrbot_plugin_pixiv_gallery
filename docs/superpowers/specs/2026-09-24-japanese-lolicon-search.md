# Japanese Pixiv Tag Search and Lolicon Fallback — Approved Requirements

Approved by the user on 2026-09-24.

## Behavior
- Natural-language LLM tool instructions require converting user intent into concise, existing Japanese Pixiv tag terms before calling the tool. Do not add a translation service or API credential.
- Keyword searches call Lolicon API v2 first with SFW-only `r18=0`, one candidate, and Japanese `tag` values. Do not include or enforce the bookmark-tier setting on Lolicon candidates. Lolicon `uid`/`pid` are identifiers only: retrieve the work from Pixiv, validate identity and apply current safety policy; never download the Lolicon proxy URL.
- Empty Lolicon results, API errors, or inability to retrieve an eligible Pixiv work fall back to Pixiv tag search with the same Japanese keywords plus the configured bookmark-tier tag.
- Explicit `artist_id` and `illust_id` requests bypass Lolicon and tag translation, and use Pixiv endpoints. Keep existing feature toggles and report safe diagnostic category/HTTP status without tokens or raw response bodies.
- Add a configurable bookmark-tier selection with exactly: `100users入り`, `500users入り`, `1000users入り`, `5000users入り`, `10000users入り`, `50000users入り`, `100000users入り`. Default: `100users入り`. Expose it through AstrBot config and Plugin Pages.
- Pixiv images must use original-image URLs returned by Pixiv and the image download request must send `Referer: https://www.pixiv.net/`. Preserve all existing download safety checks and current content-safety filters.
- Verify supplied sample artist ID `1893126` and illustration ID `128997681` through request construction/response-normalization regression tests; no live Pixiv account credentials are available, so do not claim live authenticated validation.

## Non-goals
- No image downloads through Lolicon's proxy URLs.
- No additional natural-language translation provider, key, or dependency.
- No change to adult-content policy or to whether the existing explicit-ID feature toggles default off.
- Do not apply bookmark-tag search semantics to explicit artist/illustration ID requests.

## Release
- Set plugin metadata and Page version to `0.1.3`, document changes in the changelog, verify, merge into `main`, and push. Do not create a GitHub Release unless separately requested.
