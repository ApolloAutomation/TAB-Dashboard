// The few DOM parts render.js uses, so its drawing can be checked in Node.
// No layout: positions are the style values render.js writes.

class FakeClassList {
  constructor(element) {
    this.element = element;
  }

  get names() {
    return this.element.className.split(/\s+/).filter(Boolean);
  }

  set names(list) {
    this.element.className = list.join(" ");
  }

  add(...names) {
    this.names = [...new Set([...this.names, ...names])];
  }

  remove(...names) {
    this.names = this.names.filter((name) => !names.includes(name));
  }

  contains(name) {
    return this.names.includes(name);
  }

  toggle(name, force) {
    const on = force === undefined ? !this.contains(name) : Boolean(force);
    if (on) {
      this.add(name);
    } else {
      this.remove(name);
    }
    return on;
  }
}

class FakeStyle {
  constructor() {
    this.properties = new Map();
  }

  setProperty(name, value) {
    this.properties.set(name, String(value));
  }

  removeProperty(name) {
    this.properties.delete(name);
  }

  getPropertyValue(name) {
    return this.properties.get(name) ?? "";
  }
}

export class FakeElement {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.localName = tag;
    this.className = "";
    this.classList = new FakeClassList(this);
    this.style = new FakeStyle();
    this.dataset = {};
    this.attributes = new Map();
    this.children = [];
    this.parentElement = null;
    this.listeners = new Map();
    this._text = "";
  }

  get childNodes() {
    return this.children;
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this.children = [];
    this._text = String(value);
  }

  append(...nodes) {
    for (const node of nodes) {
      node.parentElement?.removeChild(node);
      node.parentElement = this;
      this.children.push(node);
    }
  }

  removeChild(node) {
    this.children = this.children.filter((child) => child !== node);
    node.parentElement = null;
  }

  remove() {
    this.parentElement?.removeChild(this);
  }

  replaceChildren(...nodes) {
    for (const child of this.children) {
      child.parentElement = null;
    }
    this.children = [];
    this._text = "";
    this.append(...nodes);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === "class") {
      this.className = String(value);
    }
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  addEventListener(type, listener) {
    this.listeners.set(type, [...(this.listeners.get(type) || []), listener]);
  }

  getBoundingClientRect() {
    return { x: 0, y: 0, width: 0, height: 0, left: 0, top: 0, right: 0, bottom: 0 };
  }

  // Every element below this one, in document order.
  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  // Only ".class" and "tag" selectors, which is all the tests and render.js need.
  matches(selector) {
    if (selector.startsWith(".")) {
      return this.classList.contains(selector.slice(1)) || (this.getAttribute("class") || "").split(" ").includes(selector.slice(1));
    }
    return this.localName === selector;
  }

  querySelectorAll(selector) {
    return this.descendants().filter((node) => node.matches(selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

// Installs a fake document on globalThis; returns a function that removes it.
export function installFakeDom() {
  const before = globalThis.document;
  globalThis.document = {
    createElement: (tag) => new FakeElement(tag),
    createElementNS: (_ns, tag) => new FakeElement(tag),
  };
  return () => {
    globalThis.document = before;
  };
}
