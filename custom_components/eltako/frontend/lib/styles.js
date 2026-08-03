/** Styles of the Eltako panel. Uses Home Assistant theme variables, so light and dark work. */

export const STYLES = `
  :host {
    display: block;
    height: 100%;
    overflow: hidden;
    --eltako-border: var(--divider-color, rgba(127,127,127,.3));
    --eltako-muted: var(--secondary-text-color, #727272);
    --eltako-card: var(--card-background-color, #fff);
    --eltako-radius: 12px;
    color: var(--primary-text-color, #212121);
    background: var(--primary-background-color, #fafafa);
    font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
    font-size: 14px;
  }

  /* ---------------------------------------------------------------- layout */
  /* The navigation is a horizontal bar on top so that the content can use the full width. */
  .shell { display: flex; flex-direction: column; height: 100%; position: relative; }
  nav {
    flex: 0 0 auto; box-sizing: border-box; display: flex; align-items: center; gap: 4px;
    flex-wrap: wrap; padding: 8px 16px; background: var(--eltako-card);
    border-bottom: 1px solid var(--eltako-border);
  }
  nav .brand {
    display: flex; align-items: baseline; gap: 8px; margin-right: 10px; padding-right: 14px;
    border-right: 1px solid var(--eltako-border); align-self: stretch;
  }
  nav .brand ha-icon, nav .brand .glyph { align-self: center; }
  nav .brand-title { font-size: 1rem; font-weight: 500; }
  nav .brand-version { font-size: .7rem; color: var(--eltako-muted); }
  nav a {
    display: flex; align-items: center; gap: 8px; padding: 7px 12px; border-radius: 8px;
    color: var(--primary-text-color); text-decoration: none; cursor: pointer; font-size: .9rem;
    white-space: nowrap;
  }
  nav a:hover { background: var(--secondary-background-color, rgba(127,127,127,.1)); }
  nav a.active { background: color-mix(in srgb, var(--primary-color, #03a9f4) 16%, transparent);
                 color: var(--primary-color, #03a9f4); font-weight: 500; }
  nav a .badge {
    font-size: .7rem; padding: 1px 7px; border-radius: 10px;
    background: var(--label-badge-yellow, #f9a825); color: #212121;
  }
  nav ha-icon, nav .glyph { --mdc-icon-size: 20px; width: 20px; text-align: center; flex: 0 0 20px; }

  main { flex: 1 1 auto; overflow-y: auto; padding: 16px 20px 40px; box-sizing: border-box; }
  header.page-head { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: baseline;
                     justify-content: space-between; margin-bottom: 16px; }
  header.page-head h1 { margin: 0; font-size: 1.35rem; font-weight: 500; }
  header.page-head .page-subtitle { font-size: .82rem; color: var(--eltako-muted); margin-top: 3px; }
  .head-status { display: flex; flex-wrap: wrap; gap: 6px; }

  @media (max-width: 640px) {
    nav { flex-wrap: nowrap; overflow-x: auto; padding: 6px 10px; }
    nav .brand { display: none; }
    nav a span:not(.badge) { display: none; }   /* icons only, keeps the bar on one line */
    nav a.active span:not(.badge) { display: inline; }
    main { padding: 14px 14px 32px; }
  }

  /* ---------------------------------------------------------------- pieces */
  h2 { font-size: 1rem; font-weight: 500; margin: 22px 0 10px; }
  h2:first-child { margin-top: 0; }
  .pill { font-size: .75rem; padding: 3px 10px; border-radius: 12px; white-space: nowrap;
          background: var(--eltako-card); border: 1px solid var(--eltako-border); }
  .pill.on { background: var(--label-badge-green, #43a047); color: #fff; border-color: transparent; }
  .pill.off { background: var(--label-badge-red, #e53935); color: #fff; border-color: transparent; }
  .pill.warn { background: var(--label-badge-yellow, #f9a825); color: #212121; border-color: transparent; }

  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 6px; }
  .card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
          border-radius: var(--eltako-radius); padding: 13px 14px; display: flex; flex-direction: column; gap: 3px; }
  .card.warn { border-color: var(--label-badge-yellow, #f9a825); }
  .card.good { border-color: var(--label-badge-green, #43a047); }
  .card-value { font-size: 1.35rem; font-weight: 500; line-height: 1.2; }
  .card-label { font-size: .75rem; color: var(--eltako-muted); }
  .card-hint { font-size: .68rem; color: var(--eltako-muted); word-break: break-all; }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
  .tile { background: var(--eltako-card); border: 1px solid var(--eltako-border);
          border-radius: var(--eltako-radius); padding: 14px 16px; }
  .tile-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .tile-title { font-weight: 500; }
  .tile table { font-size: .8rem; }
  .tile table th { width: 45%; font-weight: 400; color: var(--eltako-muted); }

  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip { font-size: .75rem; padding: 3px 10px; border-radius: 12px; background: var(--eltako-card);
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
  button.action:hover { border-color: var(--primary-color, #03a9f4); color: var(--primary-color, #03a9f4); }
  button.action.small { padding: 2px 8px; font-size: .75rem; }
  button.action.primary { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
                          border-color: transparent; }
  button.action.danger:hover { border-color: var(--error-color, #e53935); color: var(--error-color, #e53935); }

  .table-wrapper { overflow-x: auto; background: var(--eltako-card); border: 1px solid var(--eltako-border);
                   border-radius: var(--eltako-radius); }
  table { border-collapse: collapse; width: 100%; font-size: .82rem; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--eltako-border); vertical-align: top; }
  tbody tr:last-child td { border-bottom: none; }
  thead th { position: sticky; top: 0; background: var(--eltako-card); z-index: 1; font-weight: 500;
             color: var(--eltako-muted); white-space: nowrap; }
  th[data-sort] { cursor: pointer; user-select: none; }
  th[data-sort]:hover { color: var(--primary-color, #03a9f4); }
  th[data-sort].sorted::after { content: " \\2195"; font-size: .8em; }
  tbody tr:hover { background: var(--secondary-background-color, rgba(127,127,127,.08)); }
  table.clickable tbody tr { cursor: pointer; }
  td.num, th.num { text-align: right; white-space: nowrap; }
  .mono { font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace; white-space: nowrap; }
  .hint { display: block; font-size: .7rem; color: var(--eltako-muted); white-space: normal; }
  .dir { white-space: nowrap; font-size: .75rem; }
  .dir.incoming { color: var(--label-badge-green, #43a047); }
  .dir.outgoing { color: var(--primary-color, #03a9f4); }
  .unknown-row { background: color-mix(in srgb, var(--label-badge-yellow, #f9a825) 12%, transparent); }
  .tag { font-size: .7rem; padding: 1px 7px; border-radius: 10px; white-space: nowrap; }
  .tag.taught { background: var(--label-badge-green, #43a047); color: #fff; }
  .tag.unknown { background: var(--label-badge-yellow, #f9a825); color: #212121; }
  .tag.role { background: var(--secondary-background-color, rgba(127,127,127,.15)); color: var(--eltako-muted); }
  .tag.source-yaml { background: var(--secondary-background-color, rgba(127,127,127,.15)); color: var(--eltako-muted); }
  .tag.source-ui { background: color-mix(in srgb, var(--primary-color, #03a9f4) 20%, transparent);
                   color: var(--primary-color, #03a9f4); }
  /* group rows in eltako brand blue instead of grey */
  tr.bus-device-row td { background: color-mix(in srgb, #005ca9 16%, transparent);
                         font-size: .8rem; padding-top: 9px; padding-bottom: 9px; }
  /* rows which react on a click (relation highlighting) show it */
  tbody tr[data-address] { cursor: pointer; }

  /* relation highlighting: the clicked row and everything taught in with it. One frame
     around the whole row (outline, so the collapsed cell borders play no role) instead of
     per-cell markers - no dividers inside the marked row. */
  tbody tr.relation-origin { outline: 2px solid #005ca9; outline-offset: -2px; }
  tbody tr.relation-origin td { background: color-mix(in srgb, #005ca9 20%, transparent);
                                border-bottom-color: transparent; }
  tbody tr.relation-target { outline: 2px solid var(--label-badge-green, #43a047); outline-offset: -2px; }
  tbody tr.relation-target td { background: color-mix(in srgb, var(--label-badge-green, #43a047) 22%, transparent);
                                border-bottom-color: transparent; }
  tr.bus-device-row .hint-inline, .hint-inline { font-size: .74rem; color: var(--eltako-muted); margin-left: 8px; }
  tr.channel-row td:first-child { padding-left: 20px; }
  tr.taught-in-row td { padding-left: 20px; background: color-mix(in srgb, var(--label-badge-green, #43a047) 6%, transparent); }
  tr.taught-in-row .chip { margin: 2px 4px 2px 0; }
  .tree { color: var(--eltako-muted); margin-right: 6px; }
  .bus-heading { font-size: .9rem; font-weight: 500; margin: 16px 0 8px; color: var(--eltako-muted); }
  tr.linked td:first-child { box-shadow: inset 3px 0 0 var(--primary-color, #03a9f4); }
  .stale { color: var(--label-badge-yellow, #f9a825); }

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
    border: 1px solid var(--divider-color, rgba(127,127,127,.3)); border-radius: 12px;
    box-shadow: -6px 0 24px rgba(0,0,0,.25);
    animation: eltako-drawer-in .25s ease-out;
  }
  .detail-drawer h3 { margin: 0 0 4px; }
  .detail-drawer .sensor-line { padding: 8px 0; border-bottom: 1px solid var(--divider-color, rgba(127,127,127,.2)); }
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
  .notice.warn { border-left: 4px solid var(--label-badge-yellow, #f9a825); }
  .notice h3 { margin: 0 0 8px; font-size: 1rem; font-weight: 500; }
  .notice p { margin: 6px 0; }
  pre { background: var(--secondary-background-color, rgba(127,127,127,.1)); padding: 10px;
        border-radius: 8px; overflow-x: auto; font-size: .78rem; margin: 8px 0 0; }
  code { background: var(--secondary-background-color, rgba(127,127,127,.1)); padding: 1px 5px; border-radius: 4px;
         font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace; font-size: .95em; }
  a.link { color: var(--primary-color, #03a9f4); }
  .footnote { font-size: .75rem; color: var(--eltako-muted); margin-top: 8px; }
  .links { display: flex; flex-wrap: wrap; gap: 8px; }
  .links a { display: inline-flex; align-items: center; gap: 6px; text-decoration: none;
             font-size: .85rem; padding: 7px 12px; border-radius: 8px; border: 1px solid var(--eltako-border);
             background: var(--eltako-card); color: var(--primary-text-color); }
  .links a:hover { border-color: var(--primary-color, #03a9f4); color: var(--primary-color, #03a9f4); }
`;
