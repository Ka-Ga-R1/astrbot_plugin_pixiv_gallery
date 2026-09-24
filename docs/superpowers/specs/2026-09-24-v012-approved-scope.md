# Yumeiro 0.1.2 approved scope

Approved in the task on 2026-09-24 after the defect investigation. Implement the existing plugin promises; do not redesign the interface or add unrelated features.

## Required behavior
- The AstrBot 4.28.1 natural-language tool must await image delivery and return a nonempty string for success, empty results, disabled features, invalid arguments, and safe errors. No asynchronous-generator/no-return tool result.
- Correct Pixiv OAuth client fields and signing headers, token expiry/rotation/retry, user illustration endpoint, bounded pagination, safe response normalization, and sanitized failures.
- Apply every existing configuration: default counts, total image cap, multipage choice, independent metadata/link display, per-session/user cooldown, globally bounded download concurrency, memory metadata TTL cache and clearing, context-sensitive content policy, and reject-on-unknown-safety.
- Keep R-18 and R-18G filters enabled by default. ID requests and cached data must not bypass current safety settings. Context permission never overrides an enabled global filter.
- Parse Chinese and English ID/count requests and genuine Pixiv links. Reject empty searches and invalid IDs/counts without a network request.
- Download to request-scoped temporary files and await the platform send before cleanup. Reject non-Pixiv image hosts, unsafe redirects, oversize files and non-image responses. Count only successful sends.
- Make diagnostic probes real: authentication/API, configured network path and a safe image download. Describe message-chain checks honestly; without a chat event, do not claim end-to-end delivery.
- Expose real daily statistics, activity, cache state and setting save feedback. Refresh tokens must never be returned or included in error text; rotated tokens must persist without overwriting newly saved credentials.
- Update metadata, UI, README, changelog and package/test setup to 0.1.2. Run regression/static/browser/import checks, independent review, then publish a GitHub v0.1.2 release from verified code.

## Architecture
Preserve Settings, PixivClient and PixivService. Add small safety/runtime helpers and use MessageSender as the one awaited delivery path shared by command and tool. Cache raw metadata, not context-filtered results or credentials; apply safety on every use. Images remain temporary rather than an unmanaged disk cache.

## Compatibility and validation
Python 3.10+ and the existing AstrBot APIs; verify the actual 4.28.1 tool executor contract. Production dependency is httpx, not pytest. Tests use injected transports, fake time and recording events; no real Pixiv account tokens. Report separately any live-account/platform validation that cannot be performed.
