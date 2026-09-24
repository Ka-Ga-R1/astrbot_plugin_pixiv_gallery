# Page settings and release 0.1.1 implementation plan

## Goal
Make the Pixiv refresh token setting on the Plugin Page genuinely usable, remove misleading static settings/status displays from other page views, make every settings save visibly confirm success or failure, and release version 0.1.1.

## Scope
- Backend page API: preserve secret-safe reads, accept and persist refresh token, return save metadata suitable for UI feedback, expose dynamic status/diagnostic data.
- Frontend page: add a real refresh-token input with configured-state handling, include all editable settings in save payloads, visibly show saving/success/failure states, and render overview/diagnostics from API data instead of hard-coded claims.
- Metadata/version: update plugin version and visible page version to 0.1.1.
- Tests: regression tests for backend routes and static/front-end contract checks; full pytest and compile/static checks.

## Validation strategy
1. Add failing tests for token persistence and save response metadata.
2. Add failing tests that assert the page contains a token input, submits it, uses save feedback, and does not contain known fake status literals.
3. Implement the smallest backend/frontend changes to pass.
4. Run focused tests, then full pytest, Python compile, and repository diff/audit.

## Files expected
- Modify: `main.py`, `pages/pixiv-gallery/index.html`, `pages/pixiv-gallery/app.js`, `pages/pixiv-gallery/style.css`, `metadata.yaml`
- Add/modify tests under `tests/`
- Update plan checklist as work completes.

## Completion checklist
- [x] Refresh Token is editable without exposing the stored secret.
- [x] Settings save returns a confirmation and the UI shows saving/success/failure feedback.
- [x] Overview, activity, and diagnostics use runtime data or explicit not-connected/not-implemented states.
- [x] Content safety page has a working save button.
- [x] Unimplemented cache/limit controls are no longer presented as active settings.
- [x] Version updated to 0.1.1.
- [x] Focused tests, full tests, Python compile, JavaScript syntax, and diff checks pass.
