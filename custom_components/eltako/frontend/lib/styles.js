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
  .shell { display: flex; height: 100%; }
  nav {
    flex: 0 0 216px; box-sizing: border-box; padding: 14px 10px;
    border-right: 1px solid var(--eltako-border); background: var(--eltako-card);
    display: flex; flex-direction: column; gap: 2px; overflow-y: auto;
  }
  nav .brand { display: flex; align-items: center; gap: 10px; padding: 6px 10px 14px; }
  nav .brand-title { font-size: 1.05rem; font-weight: 500; line-height: 1.15; }
  nav .brand-version { font-size: .7rem; color: var(--eltako-muted); }
  nav a {
    display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 8px;
    color: var(--primary-text-color); text-decoration: none; cursor: pointer; font-size: .9rem;
  }
  nav a:hover { background: var(--secondary-background-color, rgba(127,127,127,.1)); }
  nav a.active { background: color-mix(in srgb, var(--primary-color, #03a9f4) 16%, transparent);
                 color: var(--primary-color, #03a9f4); font-weight: 500; }
  nav a .badge {
    margin-left: auto; font-size: .7rem; padding: 1px 7px; border-radius: 10px;
    background: var(--label-badge-yellow, #f9a825); color: #212121;
  }
  nav .nav-footer { margin-top: auto; padding: 10px 12px 0; font-size: .7rem; color: var(--eltako-muted); }
  nav ha-icon, nav .glyph { --mdc-icon-size: 20px; width: 20px; text-align: center; flex: 0 0 20px; }

  main { flex: 1 1 auto; overflow-y: auto; padding: 18px 20px 40px; box-sizing: border-box; }
  header.page-head { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: baseline;
                     justify-content: space-between; margin-bottom: 16px; }
  header.page-head h1 { margin: 0; font-size: 1.35rem; font-weight: 500; }
  header.page-head .page-subtitle { font-size: .82rem; color: var(--eltako-muted); margin-top: 3px; }
  .head-status { display: flex; flex-wrap: wrap; gap: 6px; }

  @media (max-width: 780px) {
    .shell { flex-direction: column; }
    nav { flex: none; width: 100%; border-right: none; border-bottom: 1px solid var(--eltako-border);
          flex-direction: row; overflow-x: auto; align-items: center; padding: 8px; }
    nav .brand, nav .nav-footer { display: none; }
    nav a { white-space: nowrap; }
    main { padding: 14px; }
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
  .tag.unknown { background: var(--label-badge-yellow, #f9a825); color: #212121; }
  .tag.role { background: var(--secondary-background-color, rgba(127,127,127,.15)); color: var(--eltako-muted); }
  .decoded { max-width: 320px; white-space: normal; }
  .kv { display: inline-block; margin-right: 6px; font-size: .75rem; }
  .kv i { color: var(--eltako-muted); font-style: normal; margin-right: 3px; }
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
