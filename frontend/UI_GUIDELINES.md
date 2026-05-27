# Vue UI Guidelines

This frontend uses a light, calm workspace style for the AI software factory UI.
Keep new Vue components aligned with these rules unless a product requirement
explicitly calls for a different treatment.

## Visual Direction

- Use a white or near-white page background. Do not reintroduce a dark console theme.
- Make green the primary product color, supported by pale green surfaces.
- Use orange for waiting, attention, and pending decision states.
- Use sky blue, mint, and lavender only as light secondary accents for categories or metadata.
- Keep the experience airy and work-focused: readable cards, quiet borders, soft shadows, and compact but comfortable spacing.

## Color Tokens

Use the CSS variables in `src/style.css` rather than hard-coded colors:

- Background: `--bg`, `--surface`, `--surface-soft`
- Primary action and success: `--primary`, `--primary-strong`, `--primary-soft`
- Attention and waiting: `--accent-orange`, `--accent-orange-soft`
- Secondary accents: `--accent-mint`, `--accent-sky`, `--accent-lavender`
- Text and borders: `--text`, `--text-muted`, `--border`
- Destructive/error: `--red`, `--red-soft`

## Layout

- Keep the two-pane application shell: project navigation on the left, active workspace on the right.
- The sidebar should read as a light green navigation panel, not a heavy app chrome.
- The main workspace should remain white/light with card-based stage output.
- Preserve stable dimensions for fixed controls such as the sidebar, project rows, decision bar, badges, progress bars, and status dots.
- On narrow screens, stack the sidebar above the workspace and keep the decision bar visible.

## Components

- Primary buttons use green backgrounds with white text.
- Waiting or regenerate actions use orange surfaces.
- Destructive or pause actions use soft red surfaces.
- Cards use white surfaces, light green headers or accents, thin borders, and soft shadows.
- Badges are rounded pills with pale backgrounds and strong readable text.
- Inputs and textareas use white backgrounds, green focus rings, and visible borders.
- Modals use white surfaces, soft shadows, and green primary actions.

## Status Rules

- `running` and `waiting`: orange.
- `done` and successful states: green.
- `retrying`: lavender.
- `error` and destructive states: red.
- Avoid using blue as the dominant state color; reserve it for secondary metadata.

## Interaction

- The bottom decision composer must remain visible while waiting for user input.
- Feedback inputs should be easy to scan and must not overlap message content.
- Hover states should be subtle: pale green fill, slightly stronger border, or soft shadow.
- Keep transitions short and functional.

## Content Density

- Stage cards should be scannable: clear title, compact metadata, grouped content blocks.
- Long paths, API routes, and generated text must wrap safely.
- Avoid oversized hero treatments; this app is an operational workspace.

## Verification

Before shipping visual changes:

- Run `npm run build`.
- Check desktop and narrow responsive widths.
- Verify project selection, new project modal, stage expansion, and decision composer.
- Confirm text remains readable and does not overlap in the current browser viewport.
