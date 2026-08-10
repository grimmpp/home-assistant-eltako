/** Styles of the Eltako panel. Uses Home Assistant theme variables, so light and dark work. */

export const STYLES = `
  :host {
    display: block;
    height: 100%;
    overflow: hidden;
    /* Eltako brand palette. #0064AF is taken from the official logo and is also the
       dominant colour of eltako.com. On a dark theme it is too dark for text, so the accent
       switches to a lightened variant - the brand colour itself stays for surfaces.

       Everything neutral (borders, page background, hover, striping) carries a light wash of
       the brand blue instead of plain grey - that is what makes eltako.com look bright and
       blue rather than grey. The wash is mixed into the *theme* colour with color-mix, so a
       user's own Home Assistant theme keeps working and a dark theme only gets a blue cast
       instead of a hardcoded light surface. */
    --eltako-blue: #0064AF;
    --eltako-blue-light: #4C9FD8;
    --eltako-accent: var(--eltako-blue);
    --eltako-border: color-mix(in srgb, var(--eltako-blue) 20%, var(--divider-color, rgba(127,127,127,.3)));
    --eltako-muted: var(--secondary-text-color, #6C757D);
    --eltako-card: var(--card-background-color, #fff);
    /* translucent washes: they work on a light and on a dark surface alike */
    --eltako-tint: color-mix(in srgb, var(--eltako-blue) 6%, transparent);
    --eltako-tint-strong: color-mix(in srgb, var(--eltako-blue) 13%, transparent);
    --eltako-hover: color-mix(in srgb, var(--eltako-blue) 9%, transparent);
    /* Attention states. The amber of the Home Assistant badges is a strong orange and was the
       reason the whole ui read as "orange and grey" - it marks real warnings only now. The
       neutral counters next to the navigation entries carry the brand blue instead. */
    --eltako-warn: var(--label-badge-yellow, #F0A202);
    --eltako-radius: 12px;
    color: var(--primary-text-color, #212121);
    background: color-mix(in srgb, var(--eltako-blue) 4%, var(--primary-background-color, #FAFBFC));
    font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
    font-size: 14px;
  }

  /* Home Assistant themes do not expose "is dark", so the media query is the signal that
     works for the default light/dark themes. */
  @media (prefers-color-scheme: dark) {
    :host { --eltako-accent: var(--eltako-blue-light); }
  }

  /* ---------------------------------------------------------------- layout */
  /* App header (menu button + title) above the horizontal navigation bar. The menu button
     is the standard home assistant one: it shows the hamburger when the sidebar is hidden,
     so the panel can be left again on a smartphone. */
  .shell { display: flex; flex-direction: column; height: 100%; position: relative; }
  /* Large "Eltako" lettering as a watermark behind the page. It is drawn as a css mask of
     img/eltako-watermark.svg (the bare lettering, no blue square) filled with the brand
     colour, so it follows the theme instead of being a baked-in grey - on a dark theme the
     lighter blue keeps it visible at the same faint strength. The url comes from the panel
     as --eltako-watermark, because a relative url() in this stylesheet would be resolved
     against the *document*, not against the frontend folder.
     It is absolutely positioned, so it is no flex item of .shell and does not scroll with
     <main>; .topbar and main paint above it. */
  .shell::before {
    content: ""; position: absolute; inset: 0; z-index: 0; pointer-events: none;
    background-color: var(--eltako-blue);
    /* barely there: the lettering must read as a shade of the background, not as content */
    opacity: .05;
    -webkit-mask: var(--eltako-watermark) no-repeat center 55% / min(70%, 760px) auto;
    mask: var(--eltako-watermark) no-repeat center 55% / min(70%, 760px) auto;
  }
  /* the dark brand blue disappears completely on a dark background - there the watermark uses
     the lightened variant, which reads as the same faint shade of the page */
  @media (prefers-color-scheme: dark) {
    .shell::before { background-color: var(--eltako-blue-light); opacity: .07; }
  }
  /* header + navigation: one white bar, and the reference for the logo positioned in it */
  .topbar { flex: 0 0 auto; position: relative; z-index: 1; }
  header.app-head {
    flex: 0 0 auto; box-sizing: border-box; display: flex; align-items: center; gap: 10px;
    /* more room below: the navigation used to sit directly under the title */
    padding: 8px 84px 6px 16px; background: var(--eltako-card); min-height: 64px;
  }
  header.app-head .brand {
    display: flex; align-items: center; gap: 10px; min-width: 0; overflow: hidden; flex: 0 1 auto;
  }
  /* Switch between the simple and the expert view: the last element of the navigation bar,
     right aligned. position:sticky keeps it at the right edge when the navigation scrolls
     horizontally on a phone - the right offset is the space the logo occupies. */
  nav .mode-switch {
    margin-left: auto; flex: 0 0 auto; position: sticky; right: 84px;
    display: inline-flex; gap: 1px; padding: 2px; border-radius: 999px;
    border: 1px solid var(--eltako-border);
    background: color-mix(in srgb, var(--eltako-blue) 6%, var(--eltako-card));
  }
  nav .mode-switch button {
    font: inherit; font-size: .72rem; display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 9px; border: none; border-radius: 999px; background: none; cursor: pointer;
    color: var(--eltako-muted); white-space: nowrap;
  }
  nav .mode-switch button:hover { color: var(--eltako-accent); }
  nav .mode-switch button.active {
    background: var(--eltako-accent); color: var(--text-primary-color, #fff); font-weight: 500;
  }
  nav .mode-switch ha-icon, nav .mode-switch .glyph {
    --mdc-icon-size: 14px; width: 14px; flex: 0 0 14px;
  }
  header.app-head .brand-title {
    font-size: 1.35rem; font-weight: 600; letter-spacing: .02em; color: var(--eltako-accent);
    white-space: nowrap;
  }
  header.app-head .brand-version { font-size: .7rem; color: var(--eltako-muted); }
  /* a version which is not a finished release says so, everywhere the version is shown */
  .prerelease-tag { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 999px;
                    font-size: .68rem; font-weight: 600; text-transform: uppercase;
                    letter-spacing: .03em; color: var(--eltako-warn);
                    border: 1px solid var(--eltako-warn);
                    background: color-mix(in srgb, var(--eltako-warn) 12%, transparent); }
  header.app-head ha-icon, header.app-head .glyph {
    --mdc-icon-size: 22px; color: var(--eltako-accent); flex: 0 0 auto;
  }
  /* The official Eltako logo at the right edge of the white bar. The bar is the header *and*
     the navigation below it - both share the card background - so the logo lives in .topbar
     and is centred over their combined height. Inside the header it would sit in the upper
     half of the white area. It is a square tile with its own background colour, so it needs
     no theme handling - only rounded corners so it does not clash with the rest of the ui. */
  .topbar .brand-logo {
    position: absolute; right: 16px; top: 50%; transform: translateY(-50%);
    height: 52px; width: auto; border-radius: 6px; display: block;
  }
  @media (max-width: 640px) {
    header.app-head .brand-title {
      font-size: 1.05rem; overflow: hidden; text-overflow: ellipsis;
    }
    .topbar .brand-logo { height: 40px; right: 10px; }
  }
  header.app-head .menu-fallback {
    background: none; border: none; cursor: pointer; font-size: 20px; padding: 6px 8px;
    margin-left: -8px; color: var(--primary-text-color); border-radius: 8px;
  }
  header.app-head .menu-fallback:hover { background: var(--eltako-hover); }
  nav {
    flex: 0 0 auto; box-sizing: border-box; display: flex; align-items: center; gap: 6px;
    flex-wrap: wrap; padding: 2px 84px 10px 16px; background: var(--eltako-card);
    border-bottom: 1px solid var(--eltako-border);
  }
  nav a {
    display: flex; align-items: center; gap: 8px; padding: 7px 12px; border-radius: 8px;
    color: var(--primary-text-color); text-decoration: none; cursor: pointer; font-size: .9rem;
    white-space: nowrap;
  }
  nav a:hover { background: var(--eltako-hover); }
  nav a.active { background: color-mix(in srgb, var(--eltako-accent) 16%, transparent);
                 color: var(--eltako-accent); font-weight: 500; }
  nav a .badge {
    font-size: .7rem; padding: 1px 7px; border-radius: 10px;
    background: var(--eltako-accent); color: var(--text-primary-color, #fff);
  }
  nav ha-icon, nav .glyph { --mdc-icon-size: 20px; width: 20px; text-align: center; flex: 0 0 20px; }

  /* position/z-index: the page content belongs above the watermark of .shell::before */
  main { flex: 1 1 auto; overflow-y: auto; padding: 16px 20px 40px; box-sizing: border-box;
         position: relative; z-index: 1; background: transparent; }
  header.page-head { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: baseline;
                     justify-content: space-between; margin-bottom: 16px; }
  header.page-head h1 { margin: 0; font-size: 1.35rem; font-weight: 500; }
  header.page-head .page-subtitle { font-size: .82rem; color: var(--eltako-muted); margin-top: 3px; }
  .head-status { display: flex; flex-wrap: wrap; gap: 6px; }

  @media (max-width: 640px) {
    header.app-head { padding: 8px 62px 4px 10px; }
    nav { flex-wrap: nowrap; overflow-x: auto; padding: 2px 62px 8px 10px; }
    nav a span:not(.badge) { display: none; }   /* icons only, keeps the bar on one line */
    nav a.active span:not(.badge) { display: inline; }
    /* the switch stays pinned to the right; only the active view keeps its label */
    nav .mode-switch { right: 62px; }
    /* icon only, but still big enough to hit with a thumb */
    nav .mode-switch button:not(.active) span:not(.glyph) { display: none; }
    nav .mode-switch button:not(.active) { min-width: 32px; justify-content: center; }
    main { padding: 14px 14px 32px; }
  }

  /* ---------------------------------------------------------------- pieces */
  h2 { font-size: 1rem; font-weight: 500; margin: 22px 0 10px; }
  h2:first-child { margin-top: 0; }
  .pill { font-size: .75rem; padding: 3px 10px; border-radius: 12px; white-space: nowrap;
          background: var(--eltako-card); border: 1px solid var(--eltako-border); }
  .pill.on { background: var(--label-badge-green, #43a047); color: #fff; border-color: transparent; }
  .pill.off { background: var(--label-badge-red, #e53935); color: #fff; border-color: transparent; }
  .pill.warn { background: var(--eltako-warn); color: #212121; border-color: transparent; }
  a.pill.link { color: var(--eltako-accent); text-decoration: none; }
  a.pill.link:hover { border-color: var(--eltako-accent); }

  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 6px; }
  .card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
          border-radius: var(--eltako-radius); padding: 13px 14px; display: flex; flex-direction: column; gap: 3px; }
  .card.warn { border-color: var(--eltako-warn); }
  .card.good { border-color: var(--label-badge-green, #43a047); }
  .card-value { font-size: 1.35rem; font-weight: 500; line-height: 1.2; }
  .card-label { font-size: .75rem; color: var(--eltako-muted); }
  /* 'anywhere' instead of 'break-all': a long serial path or address still breaks, but a hint
     written as a sentence is wrapped at its word boundaries and stays readable. */
  .card-hint { font-size: .68rem; color: var(--eltako-muted); overflow-wrap: anywhere; }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
  .tile { background: var(--eltako-card); border: 1px solid var(--eltako-border);
          border-radius: var(--eltako-radius); padding: 14px 16px; }
  .tile-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .tile-title { font-weight: 500; }
  .tile table { font-size: .8rem; }
  .tile table th { width: 45%; font-weight: 400; color: var(--eltako-muted); }

  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  /* inline-block and nowrap are what keeps a chip in one piece: an inline element does not
     grow the line box by its vertical padding, so as soon as chips wrap onto a second line
     (a table cell of the help page holds dozens of device names) their borders overlap -
     and a device name with a hyphen would be broken in the middle. */
  .chip { display: inline-block; white-space: nowrap;
          font-size: .75rem; padding: 3px 10px; border-radius: 12px; background: var(--eltako-card);
          border: 1px solid var(--eltako-border); }

  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
  .toolbar .spacer { flex: 1 1 auto; }
  input[type=search], select, input[type=number] {
    font: inherit; font-size: .85rem; padding: 6px 10px; border-radius: 8px; min-width: 190px;
    border: 1px solid var(--eltako-border); background: var(--eltako-card); color: var(--primary-text-color);
  }
  label.check { font-size: .85rem; display: inline-flex; gap: 5px; align-items: center; }
  button.action {
    font: inherit; font-size: .85rem; padding: 6px 12px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--eltako-border); background: var(--eltako-card); color: var(--primary-text-color);
  }
  button.action:hover { border-color: var(--eltako-accent); color: var(--eltako-accent); }
  button.action.small { padding: 2px 8px; font-size: .75rem; }
  button.action.primary { background: var(--eltako-accent); color: var(--text-primary-color, #fff);
                          border-color: transparent; }
  button.action.danger:hover { border-color: var(--error-color, #e53935); color: var(--error-color, #e53935); }
  /* a disabled button has to look disabled - otherwise a running test looks startable */
  button.action:disabled, button.action:disabled:hover {
    opacity: .45; cursor: not-allowed; border-color: var(--eltako-border); color: var(--primary-text-color);
  }
  button.action.primary:disabled, button.action.primary:disabled:hover {
    border-color: transparent; color: var(--text-primary-color, #fff);
  }

  /* Translucent, so the watermark of .shell::before shows through the tables instead of being
     cut off by the largest surface of the page. The card colour is mixed with transparency
     instead of being replaced, so a custom or dark theme keeps its own surface.
     60% is what makes the lettering readable *through* the table: the watermark itself is only
     5% strong, so a nearly opaque table (80%) leaves a difference of one percent - present in
     the css and invisible on a screen. The text of the table is opaque and unaffected. */
  .table-wrapper { overflow-x: auto; background: color-mix(in srgb, var(--eltako-card) 60%, transparent);
                   border: 1px solid var(--eltako-border);
                   border-radius: var(--eltako-radius); }
  table { border-collapse: collapse; width: 100%; font-size: .82rem; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--eltako-border); vertical-align: top; }
  tbody tr:last-child td { border-bottom: none; }
  /* the head stays opaque on purpose: it is sticky, so the rows scroll underneath it - through a
     translucent head they would show as ghosts */
  thead th { position: sticky; top: 0; background: var(--eltako-card); z-index: 1; font-weight: 500;
             color: var(--eltako-muted); white-space: nowrap; }
  th[data-sort] { cursor: pointer; user-select: none; }
  th[data-sort]:hover { color: var(--eltako-accent); }
  th[data-sort].sorted::after { content: " \\2195"; font-size: .8em; }
  tbody tr:hover { background: var(--eltako-hover); }
  table.clickable tbody tr { cursor: pointer; }
  td.num, th.num { text-align: right; white-space: nowrap; }
  .mono { font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace; white-space: nowrap; }
  .hint { display: block; font-size: .7rem; color: var(--eltako-muted); white-space: normal; }
  .dir { white-space: nowrap; font-size: .75rem; }
  .dir.incoming { color: var(--label-badge-green, #43a047); }
  .dir.outgoing { color: var(--eltako-accent); }
  .unknown-row { background: var(--eltako-tint); }
  .tag { font-size: .7rem; padding: 1px 7px; border-radius: 10px; white-space: nowrap; }
  .tag.taught { background: var(--label-badge-green, #43a047); color: #fff; }
  .tag.unknown { background: var(--eltako-warn); color: #212121; }
  .tag.role { background: var(--eltako-tint-strong); color: var(--eltako-muted); }
  .tag.source-yaml { background: var(--eltako-tint-strong); color: var(--eltako-muted); }
  .tag.source-ui { background: color-mix(in srgb, var(--eltako-accent) 20%, transparent);
                   color: var(--eltako-accent); }
  /* Simulated: no hardware behind it. Deliberately loud and used in EVERY list, so a
     simulated device can never be mistaken for a real one. */
  .tag.simulated { background: var(--eltako-warn); color: #212121; font-weight: 600;
                   letter-spacing: .02em; }
  .tag.simulated::before { content: "⚗ "; }
  /* a row/card of a simulated device carries the same signal without shouting */
  tr.simulated-row td:first-child { box-shadow: inset 3px 0 0 var(--eltako-warn); }
  /* group rows in eltako brand blue instead of grey */
  tr.bus-device-row td { background: var(--eltako-tint-strong);
                         font-size: .8rem; padding-top: 9px; padding-bottom: 9px; }
  /* rows which react on a click (relation highlighting) show it */
  tbody tr[data-address] { cursor: pointer; }

  /* relation highlighting: the clicked row and everything taught in with it. One frame
     around the whole row (outline, so the collapsed cell borders play no role) instead of
     per-cell markers - no dividers inside the marked row. */
  tbody tr.relation-origin { outline: 2px solid var(--eltako-accent); outline-offset: -2px; }
  tbody tr.relation-origin td { background: color-mix(in srgb, var(--eltako-blue) 20%, transparent);
                                border-bottom-color: transparent; }
  tbody tr.relation-target { outline: 2px solid var(--label-badge-green, #43a047); outline-offset: -2px; }
  tbody tr.relation-target td { background: color-mix(in srgb, var(--label-badge-green, #43a047) 22%, transparent);
                                border-bottom-color: transparent; }
  tr.bus-device-row .hint-inline, .hint-inline { font-size: .74rem; color: var(--eltako-muted); margin-left: 8px; }
  tr.channel-row td:first-child { padding-left: 20px; }
  tr.taught-in-row td { padding-left: 20px; background: color-mix(in srgb, var(--label-badge-green, #43a047) 6%, transparent); }
  tr.taught-in-row .chip { margin: 2px 4px 2px 0; }

  /* candidates of an address which is not configured yet (block 'Unknown devices'):
     one line per EEP, the EEPs aligned in their own column so the device models of the
     different profiles can be compared at a glance. */
  .eep-devices { display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; align-items: baseline; }
  .eep-devices-key { font-size: .75rem; opacity: .75; white-space: nowrap; }
  .eep-devices-key::after { content: ":"; }
  .eep-devices-value { display: flex; flex-wrap: wrap; gap: 3px; align-items: baseline; }
  .eep-devices-value .chip { padding: 1px 7px; }

  /* one candidate per line in the 'Possible EEPs' column */
  .candidate { display: flex; flex-wrap: wrap; gap: 4px; align-items: baseline; margin: 1px 0; }
  .candidate .hint { flex: 1 1 100%; margin: 0; }
  .tree { color: var(--eltako-muted); margin-right: 6px; }
  .bus-heading { font-size: .9rem; font-weight: 500; margin: 16px 0 8px; color: var(--eltako-muted); }
  tr.linked td:first-child { box-shadow: inset 3px 0 0 var(--eltako-accent); }
  .stale { color: var(--eltako-warn); }

  /* side panel with the memory content (taught-in senders) of a bus device. It lives in
     #drawer-outlet of the shell (not in the scrolling <main>), so it overlays the page on
     the right and slides in - it never scrolls away with the table. */
  @keyframes eltako-drawer-in {
    from { transform: translateX(110%); }
    to   { transform: none; }
  }
  .detail-drawer {
    position: absolute; top: 64px; right: 12px; bottom: 12px; width: min(400px, 85vw);
    overflow-y: auto; z-index: 6; padding: 16px; box-sizing: border-box;
    background: var(--card-background-color, var(--eltako-card, #fff));
    border: 1px solid var(--eltako-border); border-radius: 12px;
    box-shadow: -6px 0 24px rgba(0,0,0,.25);
    animation: eltako-drawer-in .25s ease-out;
  }
  .detail-drawer h3 { margin: 0 0 4px; }
  .detail-drawer .sensor-line { padding: 8px 0; border-bottom: 1px solid var(--eltako-border); }
  .detail-drawer .sensor-line:last-child { border-bottom: none; }
  .detail-drawer .sensor-line .hint { margin-top: 2px; }

  /* a row flashes blue when a telegram of that device is received */
  @keyframes eltako-telegram-flash {
    0%   { background-color: color-mix(in srgb, var(--info-color, #039be5) 55%, transparent); }
    35%  { background-color: color-mix(in srgb, var(--info-color, #039be5) 40%, transparent); }
    100% { background-color: transparent; }
  }
  tbody tr.telegram-flash { animation: eltako-telegram-flash 1.4s ease-out; }
  tbody tr.telegram-flash td:first-child { box-shadow: inset 3px 0 0 var(--info-color, #039be5); }
  td.actions { white-space: nowrap; display: flex; gap: 6px; align-items: center; }
  .decoded { max-width: 320px; white-space: normal; }
  .kv { display: inline-block; margin-right: 6px; font-size: .75rem; }
  .kv i { color: var(--eltako-muted); font-style: normal; margin-right: 3px; }
  .kv.more { color: var(--eltako-muted); }
  tr.detail { display: none; }
  tr.detail.visible { display: table-row; }
  tr.detail pre { margin: 0; font-size: .72rem; overflow-x: auto; }

  .empty, .notice { background: var(--eltako-card); border: 1px solid var(--eltako-border);
                    border-radius: var(--eltako-radius); padding: 16px; font-size: .88rem; }
  .notice { margin-bottom: 12px; }
  .notice.warn { border-left: 4px solid var(--eltako-warn); }
  .notice h3 { margin: 0 0 8px; font-size: 1rem; font-weight: 500; }
  .notice p { margin: 6px 0; }
  pre { background: var(--eltako-tint); padding: 10px;
        border-radius: 8px; overflow-x: auto; font-size: .78rem; margin: 8px 0 0; }
  code { background: var(--eltako-tint); padding: 1px 5px; border-radius: 4px;
         font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace; font-size: .95em; }
  a.link { color: var(--eltako-accent); }
  .footnote { font-size: .75rem; color: var(--eltako-muted); margin-top: 8px; }
  .links { display: flex; flex-wrap: wrap; gap: 8px; }
  .links a { display: inline-flex; align-items: center; gap: 6px; text-decoration: none;
             font-size: .85rem; padding: 7px 12px; border-radius: 8px; border: 1px solid var(--eltako-border);
             background: var(--eltako-card); color: var(--primary-text-color); }
  .links a:hover { border-color: var(--eltako-accent); color: var(--eltako-accent); }
`;
