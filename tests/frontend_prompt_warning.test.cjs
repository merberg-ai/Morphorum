'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const image = fs.readFileSync(path.join(root, 'assets/image.js'), 'utf8');
const animation = fs.readFileSync(path.join(root, 'assets/animation.js'), 'utf8');

test('image generation exposes exact job prompt warnings in a persistent view', () => {
  assert.match(html, /id="image-prompt-token-warning"/);
  assert.match(image, /Array\.isArray\(job\.prompt_warnings\)/);
  assert.match(image, /showImagePromptWarnings\(job\)/);
  assert.match(image, /previewImagePromptLength/);
});
test('animation editor includes an SDXL-only prompt length advisory', () => {
  assert.match(html, /id="animation-prompt-token-warning"/);
  assert.match(animation, /showAnimationPromptLengthAdvisory/);
  assert.match(animation, /family !== 'sdxl'/);
});
