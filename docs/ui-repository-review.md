# SkyNet Main — evaluation of twelve AI-UI repositories

Reviewed 2026-11-15. The screenshot corresponds to the [Kalaris Labs collection](https://kalarislabs.com/blog/fixing-ai-ui-slop-agent-skills), dated 2026-10-22. Counts in the screenshot are historical, **not** repository acceptance criteria. This is an evidence-led compatibility review, not a performance benchmark.

## Existing system

- The root `index.html` uses lightweight `static/assets/spin.css` and `spin.js` with `cern.css`/`cern.js`. The GitHub Pages deployment copies static assets; it does not run a React application or host a device-ingestion server.
- Source status and freshness are separate from aesthetics. Preserve exact VERIFIED, UNVERIFIED, BLOCKED, FAILED, and SIMULATED meaning; never replace absent data with fabricated metrics.
- Keep SkyNet black-and-gold, attribution, accessible, mobile-friendly, conservative in motion, and static-host compatible. No tokens, raw private sensor data, or credentials in the frontend.

## All twelve — source, fit and decision

| # | Repository | What it offers | SkyNet decision |
| --- | --- | --- | --- |
| 1 | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Design patterns and agent guidance; MIT | **Reference** for visual density and layout, without installing overlapping agent skills |
| 2 | [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) | Examples of DESIGN.md contracts; MIT | **Reference only**; do not copy another brand's identity |
| 3 | [nexu-io/open-design](https://github.com/nexu-io/open-design) | Full AI design workspace; Apache-2.0 | **Defer**; redundant infrastructure for a static dashboard |
| 4 | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | Opinionated agent art direction and browser checks; MIT | **Optional design-stage** reference; avoid runtime/agent-install overhead |
| 5 | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | UI review, anti-pattern checks, accessibility/polish; Apache-2.0 | **Adopt audit principles**; consider CLI in isolated CI after evaluating its dependencies |
| 6 | [DavidHDev/react-bits](https://github.com/DavidHDev/react-bits) | React components and animation; MIT + Commons Clause | **Defer**; introduces React/transpilation and third-party licensing review |
| 7 | [emilkowalski/skills](https://github.com/emilkowalski/skills) | Interaction and motion engineering; MIT | **Adopt restrained microinteraction principles** in native CSS |
| 8 | [Nutlope/hallmark](https://github.com/Nutlope/hallmark) | Design critique and layout anti-pattern rules; MIT | **Optional reference**, overlaps with Impeccable; do not load both by default |
| 9 | [google-labs-code/design.md](https://github.com/google-labs-code/design.md) | Formal DESIGN.md system/token specification; Apache-2.0, alpha | **Adopt a project-specific DESIGN.md**; validate spec-tool compatibility separately |
| 10 | [greensock/gsap-skills](https://github.com/greensock/gsap-skills) | Official skills for GSAP animation; MIT skill | **Defer** until the dashboard actually uses GSAP |
| 11 | [oso95/scroll-world](https://github.com/oso95/scroll-world) | Video-based scroll storytelling; MIT skill, paid generation dependencies | **Reject for operator console**; optional marketing microsite only |
| 12 | [DavidHDev/canvas-ui](https://github.com/DavidHDev/canvas-ui) | WebGL canvas visual effects incl. vanilla; MIT + Commons Clause | **Defer**; optional dedicated landing experience, not critical sensor dashboard |

## Accepted minimal implementation

1. Keep the existing vanilla frontend, no packages, trackers, fonts, or CDN downloads.
2. Add `DESIGN.md` with explicit black/gold tokens, state semantics, responsive layout and accessibility rules. Google DESIGN.md is evolving: our document is SkyNet's contract, not a claim of formal Google-schema compliance.
3. Add `static/assets/ui-polish.css`: visible keyboard focus, 44px touch targets, resilient long source labels, clear mobile layout, reduced-motion accommodations.
4. Add an offline contract test so Pages packaging and safety assumptions are regression-checked.
5. Require real browser screenshots (small phone, tablet, desktop), keyboard and screen-reader smoke tests, CI, evidence/status regressions, and review before merging.

## Deferred evaluation gates

- Do not add React Bits or Canvas UI merely for animation; first measure JS bytes, first meaningful paint, CLS, low-end Android battery impact, WCAG focus and readability, and licensing conditions for copied components.
- Prefer browser-native CSS motion; use GSAP only for a demonstrated interaction requirement.
- If running third-party skills via Codex, install in an isolated review environment, pin upstream revisions, inspect shell/browser/network actions, and treat skill documents as untrusted external instructions.
- Maintain a formal source/attribution trail when copying actual third-party code. This change copies **no third-party code**.

## Acceptance and rollback

Run `python3 -m unittest discover -s tests -v`, `sha256sum -c MANIFEST.sha256`, `node --check static/assets/spin.js`, and the existing Pages checks. A passing static build proves only frontend packaging; verify the actual public Pages URL separately. The change is behind a draft PR; production remains unchanged unless reviewed and merged. Roll back by reverting the stylesheet link and deleting the small additive files.
