# SkyNet Main — DESIGN.md

**Project:** SkyNet Main / 918 Technologies — evidence-first operator console  
**Status:** Project-specific human-readable design contract, inspired by the DESIGN.md ecosystem. **Not yet validated against the evolving Google DESIGN.md alpha schema.**

## Brand and visual tokens

The application uses native CSS with no webfont requirement. Source of truth for existing values: `static/assets/spin.css`.

| Token | Value | Intended usage |
| --- | --- | --- |
| `--gold` | `#e7b84b` | Operator navigation/accent; **never** evidence of VERIFIED by itself |
| `--ink` | `#070807` | Primary background |
| `--line` | `#332b19` | Subtle separators |
| `--muted` | `#aaa697` | Secondary explanatory copy |
| `--red` | `#ff675f` | FAILED/BLOCKED semantics only when explicitly labeled |
| `--green` | `#58d68d` | VERIFIED semantic text, only with scoped evidence |
| `--ui-focus` | `#fff0bd` | Keyboard focus |
| `--ui-surface-raised` | `#191a13` | Secondary UI surface |
| `--ui-motion-fast` | `160ms` | Optional tiny focus/hover transitions |

Preferred font: system UI stack; numerical measurements use tabular figures. Brand visual language: black/gold, restrained geometric surface, clear content hierarchy rather than decorative gradients/shaders.

## Evidence and trust

- Never visually equate source reachable with sensor verified. Maintain `VERIFIED`, `UNVERIFIED`, `BLOCKED`, `FAILED`, `SIMULATED`, and explicit age/freshness distinctions.
- Every live-looking card needs a direct data source, observed or collection timestamp, and evidence classification. Stale or missing values are not zeros.
- GitHub Pages is a static frontend only. Telemetry/authenticated uplinks require a separately verified gateway.
- Never show secrets or manually supplied credentials in URLs, DOM, local storage, public Pages artifacts, or logs.

## Components and layout

- Reuse `nav`, `.view`, `.metrics`, `.cards`, `.grid`, `.row`, `.badge` from `spin.css`; do not duplicate framework components.
- Mobile (<801px): navigation scrolls horizontally; preserve operable labels and 44px minimum tap targets.
- Narrow mobile (<481px): single-column data cards, no forced horizontal viewport scroll.
- Desktop: summaries are scan-friendly and bounded; avoid dead decorative cards and multiple competing ambient animations.
- Make long observation and provenance strings wrap instead of overflowing.

## Accessibility and motion

- All interactive elements should be reachable with the keyboard and retain visible focus.
- Buttons and links must have descriptive text; simulated actions must say they are simulated.
- Respect `prefers-reduced-motion`; no interface operation depends on an animation.
- Do not place real critical data solely in color, an animation, hover, or icon. Use real text labels.
- Never hijack focus, enable camera/mic/location automatically, or open external links without user action.

## Verification checklist

Before deploying changed UI, require: CI unit tests and manifest, locally served browser check, 375px/768px/1440px viewport screenshots, keyboard tab order, minimum 44px touch hit areas, focus indicators, readable high contrast, reduced-motion check, source freshness/error screens, links, and no data-source/API/gateway regressions. These checks are planned gates, not claims of completed physical or browser acceptance.
