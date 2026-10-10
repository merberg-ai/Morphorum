'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'dist',
  'assets', 'motion-lab-frame-player.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'), 'utf8');

function createPlayer() {
  const controls = () => ({
    textContent:'', value:'0', max:'1', checked:true, hidden:true,
    handlers:{},
    addEventListener(name, fn) {this.handlers[name] = fn;},
    setAttribute(name,value){this[name]=value;},
    getAttribute(name){return this[name] || null;},
    removeAttribute(name){delete this[name];},
  });
  const root=controls(), image=controls(), play=controls(), reset=controls();
  const loop=controls(), scrub=controls(), time=controls();
  let tick=null, current=0;
  const ctx={window:{},performance:{now:()=>current},
    requestAnimationFrame(fn){tick=fn;return 1;},
    cancelAnimationFrame(){tick=null;}};
  vm.runInNewContext(src,ctx);
  const player=new ctx.window.MorphorumMotionFramePlayer({
    root,image,play,reset,loop,scrub,time,getAudio:()=>null,
    shouldSync:()=>false,status:()=>{},
  });
  return {player,root,image,play,reset,loop,scrub,time,
    clock(value){current=value; if(tick)tick(value);}};
}

test('ML3.3 seeks across captured samples using project frame numbers',()=>{
  const {player,scrub,image,clock}=createPlayer();
  player.load({id:'motion-example',result:{fps:12,source_frames:196,
    captured_frame_numbers:[0,50,100,150,195],frame_player_samples:5}});
  assert.equal(scrub.max,'195');
  player.seek(121);
  assert.equal(scrub.value,'121');
  assert.match(image.src,/\/frames\/2$/);
  player.seek(195);
  assert.match(image.src,/\/frames\/4$/);
  player.play();
  clock(1000);
  assert.equal(player.frame,11);
  player.pause();
  assert.equal(player.active,false);
});

test('ML3.3 has accessible seek, play, pause, loop and frame player status',()=>{
  for(const id of ['animation-motion-frame-player','animation-motion-frame-play',
    'animation-motion-frame-scrub','animation-motion-frame-loop',
    'animation-motion-frame-time','animation-motion-frame-image']) {
    assert.ok(html.includes('id="'+id+'"'));
  }
  assert.match(html,/motion-lab-frame-player\.js/);
});
