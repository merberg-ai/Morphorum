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
  const rangeEnabled=controls(),rangeStart=controls(),rangeEnd=controls();
  const frameEvents=[],loadEvents=[];
  let tick=null, current=0;
  const ctx={window:{},performance:{now:()=>current},
    requestAnimationFrame(fn){tick=fn;return 1;},
    cancelAnimationFrame(){tick=null;}};
  vm.runInNewContext(src,ctx);
  const player=new ctx.window.MorphorumMotionFramePlayer({
    root,image,play,reset,loop,scrub,time,getAudio:()=>null,
    shouldSync:()=>false,status:()=>{},rangeEnabled,rangeStart,rangeEnd,
    onFrame:event=>frameEvents.push({...event}),
    onLoad:event=>loadEvents.push({...event}),
  });
  return {player,root,image,play,reset,loop,scrub,time,rangeEnabled,rangeStart,
    rangeEnd,frameEvents,loadEvents,
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
  assert.equal(player.frame,12);
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

test('ML3.4 has distinct preview quality options and default balanced mode',()=>{
  assert.match(html,/id="animation-motion-preview-quality"/);
  assert.match(html,/<option value="fast">/);
  assert.match(html,/<option value="balanced" selected>/);
  assert.match(html,/<option value="detailed">/);
});

test('MS5.1 A/B review plays exact bounded project frames and loops at B',()=>{
  const h=createPlayer();
  h.player.load({id:'ab',result:{fps:10,source_frames:100,
    captured_frame_numbers:[0,20,40,60,80,99]}});
  assert.equal(h.rangeEnd.value,'99');
  assert.equal(h.rangeEnabled.checked,false);
  assert.ok(h.player.setReviewRange(22,35,true));
  assert.equal(h.rangeStart.value,'22');
  assert.equal(h.rangeEnd.value,'35');
  assert.equal(h.player.frame,22);
  h.player.play();
  h.clock(500); // project frame 27
  assert.equal(h.player.frame,27);
  h.clock(1500); // relative 15 frames, wrap inside 14-frame window
  assert.equal(h.player.frame,23);
  assert.match(h.image.src,/\/frames\/1$/);
  assert.equal(h.frameEvents.at(-1).previewSampleFrame,20);
  h.player.pause();
  assert.ok(h.loadEvents.length===1);
  assert.deepEqual(h.loadEvents[0],{fps:10,frames:100,samples:6});
});

test('MS5.1 non-loop playback stops precisely at selected B',()=>{
  const h=createPlayer();
  h.player.load({id:'stop',result:{fps:24,source_frames:48,
    captured_frame_numbers:[0,10,20,30,47]}});
  assert.ok(h.player.setReviewRange(12,18,true));
  h.loop.checked=false;
  h.player.play();
  h.clock(2000);
  assert.equal(h.player.frame,18);
  assert.equal(h.player.active,false);
  assert.equal(h.play.textContent,'▶ Play');
  assert.equal(h.scrub.value,'18');
  assert.equal(h.player.reviewRange().limited,true);
  assert.equal(h.player.setReviewRange(-1,3),false);
  assert.equal(h.player.setReviewRange(3,48),false);
  assert.equal(h.player.setReviewRange(15,12),false);
});

test('MS5.1 rejects corrupt preview timing and sample map before playback',()=>{
  const h=createPlayer();
  const make=result=>()=>h.player.load({id:'bad',result});
  assert.throws(make({fps:0,source_frames:24}),/FPS/);
  assert.throws(make({fps:24,source_frames:0}),/FPS/);
  assert.throws(make({fps:24,source_frames:24,
    captured_frame_numbers:[0,12,12,23]}),/sample frame map/);
  assert.throws(make({fps:24,source_frames:24,
    captured_frame_numbers:[0,24]}),/sample frame map/);
  assert.equal(h.root.hidden,true);
  assert.equal(h.player.jobId,null);
  h.player.load({id:'good',result:{fps:12,source_frames:3,
    captured_frame_numbers:[0,2]}});
  assert.equal(h.root.hidden,false);
  assert.equal(h.player.jobId,'good');
});

test('MS5.1 exposes accessible A/B review and take selection on preview panel',()=>{
  for(const id of ['animation-motion-review-enabled','animation-motion-review-a',
    'animation-motion-review-b','animation-motion-review-mark-a',
    'animation-motion-review-mark-b','animation-motion-review-take',
    'animation-motion-review-use-take','animation-motion-review-curves',
    'animation-motion-review-status','animation-motion-review-values']) {
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  }
});

test('MS5.1 A/B loop seeks analyzed WAV back to frame A and pauses cleanly',()=>{
  const h=createPlayer();
  const audio={
    readyState:4,duration:30,paused:true,currentTime:0,playCalls:0,pauseCalls:0,
    play(){this.paused=false;this.playCalls++;return Promise.resolve();},
    pause(){this.paused=true;this.pauseCalls++;},
  };
  h.player.getAudio=()=>audio;
  h.player.shouldSync=()=>true;
  h.player.load({id:'audio',result:{fps:10,source_frames:80,
    captured_frame_numbers:[0,20,40,60,79]}});
  assert.ok(h.player.setReviewRange(20,29,true));
  assert.equal(audio.currentTime,2);
  h.player.play();
  assert.equal(audio.currentTime,2);
  assert.equal(audio.paused,false);
  audio.currentTime=3.1; // Frame 31, two frames beyond inclusive B.
  h.clock(3100);
  assert.equal(h.player.frame,21);
  assert.equal(audio.currentTime,2.1);
  assert.ok(audio.playCalls>=2);
  h.player.pause();
  assert.equal(audio.paused,true);
});

test('MS5.1 integration compares preview against Editor FPS and frame count',()=>{
  const js=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','animation.js'),'utf8');
  assert.match(js,/function motionReviewMatch\(\)/);
  assert.match(js,/frames!==player\.count\|\|Math\.abs\(fps-player\.fps\)>1e-6/);
  assert.match(js,/function motionReviewTakeRange\(\)/);
  assert.match(js,/motionReviewSet\(layer\.start_frame,layer\.end_frame-1,true\)/);
  assert.match(js,/function motionReviewOpenCurves\(\)/);
  assert.match(js,/motionLabVisual\.setFrame\(frame\)/);
  assert.match(js,/motionReviewBind\(\)/);
  assert.match(js,/function motionReviewFrame\(\{frame,fps,frames,previewSampleFrame\}\)/);
});
