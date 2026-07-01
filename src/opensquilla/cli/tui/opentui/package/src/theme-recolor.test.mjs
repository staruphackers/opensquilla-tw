import assert from "node:assert/strict";
import test, { afterEach } from "node:test";

import { applyTheme, STATUS, THEME } from "./theme.mjs";
import { createTurnView } from "./turnView.mjs";
import { createPromptBlock } from "./blocks/promptBlock.mjs";
import { createToolBlock } from "./blocks/toolBlock.mjs";

// A live /theme switch mutates THEME/STATUS in place. Renderables captured their
// fg at creation, so a dark→light switch would leave prior transcript unreadable
// unless recolor() re-points every node at the updated tokens. These tests lock
// that contract at the node level with a minimal fake renderable.

class FakeNode {
  constructor(_renderer, options = {}) {
    Object.assign(this, options);
    this.children = [];
  }
  add(node) {
    this.children.push(node);
    return this.children.length;
  }
  remove(id) {
    this.children = this.children.filter((child) => child.id !== id);
  }
  getChildren() {
    return this.children;
  }
}

const renderer = { requestRender() {}, terminalWidth: 80, terminalHeight: 24 };

function findById(node, id) {
  for (const child of node.getChildren?.() ?? node.children ?? []) {
    if (child.id === id) return child;
    const hit = findById(child, id);
    if (hit) return hit;
  }
  return null;
}

afterEach(() => applyTheme("opensquilla-dark"));

test("prompt block recolors every node to the new theme accent", () => {
  applyTheme("opensquilla-dark");
  const box = new FakeNode();
  const block = createPromptBlock({ renderer, TextRenderable: FakeNode, box, idPrefix: "p" });
  block.begin({ text: "line one\nline two" });

  const dark = THEME.promptAccent;
  assert.ok(box.children.length >= 3);
  assert.ok(box.children.every((n) => n.fg === dark));

  applyTheme("opensquilla-light");
  block.recolor();
  assert.notStrictEqual(THEME.promptAccent, dark); // the two themes genuinely differ
  assert.ok(box.children.every((n) => n.fg === THEME.promptAccent));
});

test("tool block recolor re-derives the run-state color for its current state", () => {
  applyTheme("opensquilla-dark");
  const box = new FakeNode();
  const block = createToolBlock({ renderer, TextRenderable: FakeNode, box, idPrefix: "t" });
  block.begin({ name: "grep" });
  const node = box.children[0];
  assert.equal(node.fg, STATUS.running);

  block.update({ status: "ok" });
  assert.equal(node.fg, STATUS.ok);

  applyTheme("opensquilla-light");
  block.recolor();
  // Still the OK color, but from the new palette (not the stale dark one).
  assert.equal(node.fg, STATUS.ok);
});

test("turn card chrome recolors on a theme switch", () => {
  applyTheme("opensquilla-dark");
  const conversationBox = new FakeNode();
  const turn = createTurnView(
    {
      renderer,
      BoxRenderable: FakeNode,
      TextRenderable: FakeNode,
      MarkdownRenderable: FakeNode,
      syntaxStyle: {},
      conversationBox,
    },
    "x",
  );
  turn.begin("b1", "tool", { name: "grep" }); // opens the card (header/body/gutter)

  const box = conversationBox.children[0];
  const darkFrame = THEME.answerFrame;
  const cardTop = findById(box, "turn-x-cardtop");
  const cardBody = findById(box, "turn-x-cardbody");
  assert.ok(cardTop && cardBody);
  assert.equal(cardTop.fg, darkFrame);
  assert.equal(cardBody.borderColor, darkFrame);

  applyTheme("opensquilla-light");
  turn.recolor();
  assert.notStrictEqual(THEME.answerFrame, darkFrame);
  assert.equal(cardTop.fg, THEME.answerFrame);
  assert.equal(cardBody.borderColor, THEME.answerFrame);
});
