'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const app=fs.readFileSync(path.join(root,'assets','app.js'),'utf8');
const about=fs.readFileSync(path.join(root,'assets','about.js'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','about.css'),'utf8');

test('About is available from desktop sidebar and mobile More',()=>{
  assert.match(html,/data-view="about"/);
  assert.match(html,/data-more-view="about"/);
  assert.match(html,/id="view-about"/);
  assert.match(app,/MorphorumAbout\?\.activate\?\.\(\)/);
  assert.match(app,/'help', 'about'\]\.includes\(requested\)/);
});

test('Project credits link to known upstream work without claiming copied source',()=>{
  for (const credit of ['Deforum','Stable Diffusion WebUI Forge','chicodog530','Unlicense']) {
    assert.ok(html.includes(credit));
  }
  assert.match(html,/github\.com\/deforum\/sd-webui-deforum/);
  assert.match(html,/github\.com\/lllyasviel\/stable-diffusion-webui-forge/);
  assert.match(html,/not claims of endorsement/);
});

test('About updater is current-branch only and remains disabled by default',()=>{
  assert.match(html,/id="about-apply-update" disabled/);
  assert.match(about,/api\/about\/check/);
  assert.match(about,/api\/about\/update/);
  assert.match(about,/remote_head:selected\.remote_head/);
  assert.match(about,/!latestStatus\?\.host_local/);
  assert.match(about,/window\.MorphorumDialog\?\.confirm/);
  assert.match(about,/restart Morphorum/i);
});

test('Real optimized logo is committed and keeps its full landscape aspect ratio',()=>{
  assert.match(html,/id="about-logo-fallback"/);
  assert.match(html,/id="about-logo"/);
  assert.match(html,/src="\/assets\/morphorum-about-logo\.webp"/);
  const file=fs.readFileSync(path.join(root,'assets','morphorum-about-logo.webp'));
  assert.equal(file.toString('ascii',0,4),'RIFF');
  assert.equal(file.toString('ascii',8,12),'WEBP');
  assert.ok(file.length<100000,'Logo should be small enough to load quickly');
  assert.match(about,/naturalWidth > 0/);
  assert.match(css,/aspect-ratio:3 \/ 2/);
  assert.match(css,/@media\(max-width:640px\)/);
});
