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


test('MS5.4 A/B one-frame range is stable and reset returns to A',()=>{
  const h=createPlayer();
  h.player.load({id:'single',result:{fps:24,source_frames:48,
    captured_frame_numbers:[0,24,47]}});
  assert.ok(h.player.setReviewRange(19,19,true));
  h.player.play();
  assert.equal(h.player.frame,19);
  assert.equal(h.player.active,false);
  assert.equal(h.play.textContent,'▶ Play');
  assert.equal(h.player.tickId,null);
  assert.ok(h.player.setReviewRange(12,20,true));
  h.player.seek(18);
  h.reset.handlers.click();
  assert.equal(h.player.frame,12,'Start must respect A/B interval');
  h.player.pause();
});

for (const fps of [12,24,30,60]) {
  test('MS5.4 frame boundary, loop and exact time at '+fps+' FPS',()=>{
    const h=createPlayer();
    h.player.load({id:'fps-'+fps,result:{fps,source_frames:fps*4,
      captured_frame_numbers:[0,Math.floor(fps*2),fps*4-1]}});
    assert.ok(h.player.setReviewRange(fps,fps*2-1,true));
    h.player.play();
    h.clock(500);
    assert.equal(h.player.frame,Math.floor(fps*1.5));
    h.clock(1300);
    assert.equal(h.player.frame,fps+Math.floor(fps*.3),'A/B should wrap by project frame');
    assert.match(h.time.textContent,new RegExp('frame '+h.player.frame+'/'));
    h.player.pause();
    assert.equal(h.player.active,false);
  });
}

test('MS5.4 short WAV ends: playback transitions to wall-clock without jumping backward',()=>{
  const h=createPlayer(), notices=[];
  const audio={
    readyState:4,duration:2.5,paused:true,currentTime:0,
    playCalls:0,pauseCalls:0,
    play(){this.paused=false;this.playCalls++;return Promise.resolve();},
    pause(){this.paused=true;this.pauseCalls++;},
  };
  h.player.getAudio=()=>audio;
  h.player.shouldSync=()=>true;
  h.player.status=message=>notices.push(message);
  h.player.load({id:'short',result:{fps:10,source_frames:50,
    captured_frame_numbers:[0,10,20,30,40,49]}});
  h.loop.checked=false;
  assert.ok(h.player.setReviewRange(20,40,true));
  h.player.play();
  audio.currentTime=2.4;
  h.clock(400);
  assert.equal(h.player.frame,24);
  audio.currentTime=2.5;
  audio.paused=true;
  h.clock(500);
  assert.equal(h.player.frame,24);
  h.clock(1100);
  assert.equal(h.player.frame,30,'Video advances after WAV end');
  h.clock(2500);
  assert.equal(h.player.frame,40,'Playback stops at inclusive B');
  assert.equal(h.player.active,false);
  assert.ok(notices.some(msg=>/Soundtrack ended/.test(msg)));
  assert.ok(audio.pauseCalls>=1);
});

test('MS5.4 missing WAV, late soundtrack and disabled sync remain silent without stalling',()=>{
  const h=createPlayer(), audio={
    readyState:0,duration:NaN,paused:true,currentTime:0,
    play(){throw Error('Must not play unavailable audio');},
    pause(){this.paused=true;},
  };
  h.player.getAudio=()=>audio;
  h.player.shouldSync=()=>true;
  h.player.load({id:'missing',result:{fps:24,source_frames:120,
    captured_frame_numbers:[0,24,60,119]}});
  h.loop.checked=false;
  h.player.play();
  h.clock(1000);
  assert.equal(h.player.frame,24);
  h.player.pause();
  h.player.shouldSync=()=>false;
  h.player.play();
  h.clock(2500);
  assert.equal(h.player.frame,60);
  h.player.pause();
});

test('MS5.4 seek with invalid frame never produces NaN URLs or audio offsets',()=>{
  const h=createPlayer(), audio={
    readyState:4,duration:10,paused:true,currentTime:0,
    play(){this.paused=false;return Promise.resolve();},
    pause(){this.paused=true;},
  };
  h.player.getAudio=()=>audio;
  h.player.shouldSync=()=>true;
  h.player.load({id:'bad-seek',result:{fps:12,source_frames:24,
    captured_frame_numbers:[0,10,23]}});
  h.player.seek(NaN);
  assert.equal(h.player.frame,0);
  assert.equal(audio.currentTime,0);
  assert.match(h.image.src,/\/frames\/0$/);
  h.player.seek(Infinity);
  assert.equal(h.player.frame,0);
});

test('MS5.4 disabling audio sync during playback pauses WAV and continues the same frame clock',()=>{
  const h=createPlayer();
  let enabled=true;
  const audio={
    readyState:4,duration:12,paused:true,currentTime:0,
    play(){this.paused=false;return Promise.resolve();},
    pause(){this.paused=true;},
  };
  h.player.getAudio=()=>audio;
  h.player.shouldSync=()=>enabled;
  h.player.load({id:'toggle',result:{fps:30,source_frames:180,
    captured_frame_numbers:[0,30,60,120,179]}});
  h.player.play();
  audio.currentTime=1.5;
  h.clock(500);
  assert.equal(h.player.frame,45);
  enabled=false;
  h.clock(600);
  assert.equal(h.player.frame,45);
  assert.equal(audio.paused,true);
  h.clock(1100);
  assert.equal(h.player.frame,60);
  h.player.pause();
});
