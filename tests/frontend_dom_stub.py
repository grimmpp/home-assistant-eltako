"""A minimal dom for the javascript tests of the frontend.

The web ui has no build step and no javascript test runner, so a page is rendered with node
into this stub instead of a browser. It implements exactly what the pages use - the selectors
they query, classList, closest, hidden and textContent - and parses the html a page produced,
so what is tested is the real markup and not a hand-built tree.

Prepend `DOM_STUB` to a script, then `parseHtml(page.render(ctx))` gives the root element.
"""

DOM_STUB = r"""
/* ------------------------------------------------------------------ dom stub */

const VOID_TAGS = new Set(['input', 'img', 'br', 'hr', 'meta', 'link']);

class El {
  constructor(tag, attributes = {}) {
    this.tagName = tag.toUpperCase();
    this.attributes = attributes;
    this.children = [];
    this.parentElement = null;
    this.hidden = 'hidden' in attributes;
    this.text = '';
    /** by event type, filled by addEventListener and fired by click() */
    this.listeners = {};
    // element.dataset.busScan <-> the attribute data-bus-scan, as in a browser
    const attributeOf = (property) =>
      'data-' + String(property).replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
    this.dataset = new Proxy({}, {
      get: (_target, property) => attributes[attributeOf(property)],
      has: (_target, property) => attributeOf(property) in attributes,
      set: (_target, property, value) => {
        attributes[attributeOf(property)] = String(value);
        return true;
      },
    });
    // enough of element.style for the pages: reading gives what the markup declared,
    // writing updates the inline style attribute again
    const declaration = {};
    for (const rule of (attributes.style || '').split(';').filter(Boolean)) {
      const [property, value] = rule.split(':');
      if (property) declaration[property.trim()] = (value || '').trim();
    }
    this.style = new Proxy(declaration, {
      set: (target, property, value) => {
        target[property] = value;
        attributes.style = Object.entries(target).map(([name, entry]) => `${name}:${entry}`).join(';');
        return true;
      },
    });
    const classes = new Set((attributes.class || '').split(/\s+/).filter(Boolean));
    this.classes = classes;
    this.classList = {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
    };
  }

  get textContent() {
    return this.children.length ? this.children.map((child) => child.textContent).join('') : this.text;
  }

  set textContent(value) {
    this.children = [];
    this.text = String(value);
  }

  getAttribute(name) {
    return name in this.attributes ? this.attributes[name] : null;
  }

  hasAttribute(name) {
    return name in this.attributes;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  append(child) {
    child.parentElement = this;
    this.children.push(child);
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  set innerHTML(html) {
    const parsed = parseHtml(String(html));
    this.children = [];
    this.text = parsed.text;
    for (const child of parsed.children) this.append(child);
  }

  matches(selector) {
    return selector.split(',').some((part) => this._matchesCompound(part.trim()));
  }

  /** descendant combinators ('.bus-scan-bar i'): matched from the right through the parents */
  _matchesCompound(selector) {
    const parts = selector.split(/\s+/).filter(Boolean);
    if (!this._matchesOne(parts.pop())) return false;
    let node = this.parentElement;
    for (const ancestor of parts.reverse()) {
      while (node && !node._matchesOne(ancestor)) node = node.parentElement;
      if (!node) return false;
      node = node.parentElement;
    }
    return true;
  }

  _matchesOne(selector) {
    for (const [, name, , value] of selector.matchAll(/\[([\w-]+)(="([^"]*)")?\]/g)) {
      if (!(name in this.attributes)) return false;
      if (value !== undefined && this.attributes[name] !== value) return false;
    }
    // an attribute value carries dots ("light.ceiling_light") - the class part is what is
    // left when the attribute selectors are cut out
    const rest = selector.replace(/\[[^\]]*\]/g, '');
    const tag = (rest.match(/^[a-zA-Z][\w-]*/) || [''])[0];
    if (tag && this.tagName !== tag.toUpperCase()) return false;
    for (const [, name] of rest.matchAll(/\.([\w-]+)/g)) {
      if (!this.classes.has(name)) return false;
    }
    return true;
  }

  querySelectorAll(selector) {
    return this.descendants().filter((element) => element.matches(selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  closest(selector) {
    for (let node = this; node; node = node.parentElement) {
      if (node.matches && node.matches(selector)) return node;
    }
    return null;
  }

  getElementById(id) {
    return this.querySelectorAll(`[id="${id}"]`)[0] || null;
  }

  /* the listeners a page registers in afterRender, and click() to fire them - that is what
     lets a test press a button of the rendered markup instead of calling the handler */

  addEventListener(type, listener) {
    (this.listeners[type] = this.listeners[type] || []).push(listener);
  }

  /** Returns the promise of the handlers, so an async click can be awaited. */
  click() {
    const event = { type: 'click', target: this, currentTarget: this,
                    preventDefault() {}, stopPropagation() {} };
    return Promise.all((this.listeners.click || []).map((listener) => listener(event)));
  }
}

/** the html entities the pages use - a browser shows the character, so the stub does too */
const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', nbsp: ' ', middot: '\u00b7',
                   hellip: '\u2026', ndash: '\u2013', mdash: '\u2014', times: '\u00d7',
                   check: '\u2713' };

function decodeEntities(text) {
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, name) => {
    if (name[0] === '#') {
      const code = name[1] === 'x' || name[1] === 'X'
        ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10);
      return isNaN(code) ? match : String.fromCodePoint(code);
    }
    return name in ENTITIES ? ENTITIES[name] : match;
  });
}

/** enough html parsing for the markup of the pages: tags, attributes and text */
function parseHtml(html) {
  const root = new El('root');
  let current = root;
  let last = 0;
  const addText = (node, raw) => {
    const text = decodeEntities(raw.replace(/\s+/g, ' ').trim());
    if (text) node.text += (node.text ? ' ' : '') + text;
  };
  for (const match of html.matchAll(/<\/?([a-zA-Z][\w-]*)([^>]*)>/g)) {
    addText(current, html.slice(last, match.index));
    last = match.index + match[0].length;
    if (match[0].startsWith('</')) {
      current = current.parentElement || root;
      continue;
    }
    const attributes = {};
    for (const attribute of match[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) {
      attributes[attribute[1]] = attribute[2] === undefined ? '' : attribute[2];
    }
    const element = new El(match[1], attributes);
    current.append(element);
    if (!VOID_TAGS.has(match[1].toLowerCase()) && !match[2].trim().endsWith('/')) current = element;
  }
  // text behind the last tag - and the whole fragment when it carries no tag at all
  addText(current, html.slice(last));
  return root;
}
"""
