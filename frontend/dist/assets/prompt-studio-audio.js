/* PS6.1: read-only project WAV event import and deterministic alignment preview. */
(function(root){
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  const KINDS=['kick','snare','highs'];
  const DIGEST=/^[0-9a-f]{64}$/;
  function frameAt(seconds,fps,maxFrames){
    if(!Number.isFinite(seconds)||seconds<0||
       !Number.isFinite(fps)||fps<=0||fps>240||
       !Number.isInteger(maxFrames)||maxFrames<1)return null;
    const frame=Math.floor(seconds*fps+0.5);
    return frame<maxFrames?frame:null;
  }
  function normalizeEvents(events,duration,fps,maxFrames,{saved=false}={}){
    if(!Array.isArray(events)||events.length>12000||!Number.isFinite(duration)||duration<=0||
       !Number.isFinite(fps)||fps<=0||!Number.isInteger(maxFrames)||maxFrames<1)
      throw Error('Invalid or oversized Motion Studio audio event source.');
    const seen=new Set(),points=[],warnings=[];
    for(const raw of events){
      if(!raw||typeof raw.id!=='string'||raw.id.length>96||
         !KINDS.includes(raw.kind)||!Number.isFinite(raw.time_seconds)||
         raw.time_seconds<0||raw.time_seconds>=duration||seen.has(raw.id)||
         (saved&&typeof raw.enabled!=='boolean')) {
        warnings.push('Ignored malformed or duplicate audio marker.');
        continue;
      }
      seen.add(raw.id);
      const frame=frameAt(raw.time_seconds,fps,maxFrames);
      const enabled=saved?raw.enabled:true;
      const drift=frame===null?null:frame/fps-raw.time_seconds;
      points.push({id:raw.id,kind:raw.kind,time_seconds:raw.time_seconds,
        enabled,strength:Number.isFinite(raw.strength)?raw.strength:null,
        frame,drift_seconds:drift});
    }
    points.sort((a,b)=>a.time_seconds-b.time_seconds||a.kind.localeCompare(b.kind)||a.id.localeCompare(b.id));
    const collisions=new Map();
    for(const p of points.filter(x=>x.enabled&&x.frame!==null)){
      collisions.set(p.frame,(collisions.get(p.frame)||0)+1);
    }
    const duplicateFrames=[...collisions].filter(([,n])=>n>1).length;
    const outOfRange=points.filter(p=>p.frame===null).length;
    if(duplicateFrames)warnings.push(duplicateFrames+' animation frame(s) contain multiple audio markers.');
    if(outOfRange)warnings.push(outOfRange+' marker(s) are past the project animation duration.');
    return {points,warnings,duplicateFrames,outOfRange,saved};
  }
  function planAlignment(tracks,events,selectedIds,lockedFrames,maxFrames){
    if(!tracks?.positive?.keyframes||!tracks?.negative?.keyframes||
       !Array.isArray(events)||!(selectedIds instanceof Set)||!(lockedFrames instanceof Set))
      throw Error('A valid Studio draft, selected markers and lock set are required.');
    const result=clone(tracks),moves=[],warnings=[];
    const anchors=result.positive.keyframes;
    const targets=events.filter(e=>selectedIds.has(e.id)&&e.enabled&&
      Number.isInteger(e.frame)&&e.frame>0&&e.frame<maxFrames);
    const unique=new Map();
    for(const event of targets){
      if(!unique.has(event.frame))unique.set(event.frame,event);
    }
    if(targets.length!==unique.size)
      warnings.push('Multiple selected beats resolve to the same frame; only the earliest is eligible.');
    const occupied=new Set(anchors.filter(p=>p.frame===0||lockedFrames.has(p.frame))
      .map(p=>p.frame));
    const available=[...unique.values()].filter(e=>!occupied.has(e.frame));
    if(anchors.length<=1)warnings.push('Create at least one positive scene after frame 0.');
    if(!available.length)warnings.push('No available in-range selected beats after protected frames are excluded.');
    // Assign chronologically, preserving scene order and exact prompt bytes.
    let previous=0,assigned=0;
    const movable=anchors.filter(p=>p.frame!==0&&!lockedFrames.has(p.frame));
    for(let i=0;i<movable.length;i++){
      const key=movable[i];
      const candidates=available.filter(e=>e.frame>previous);
      const remaining=movable.length-i-1;
      const possible=candidates.slice(0,Math.max(0,candidates.length-remaining));
      if(!possible.length){
        warnings.push('Not enough distinct chronological beats for all unlocked positive scenes.');
        break;
      }
      const preferred=possible.reduce((a,b)=>
        Math.abs(a.frame-key.frame)<=Math.abs(b.frame-key.frame)?a:b);
      key.frame=preferred.frame;
      const from=tracks.positive.keyframes.find(p=>p.value===key.value&&
        !moves.some(m=>m.from===p.frame));
      // Repeated prompt text is legal. Use original anchor position by order instead.
      moves.push({from:movable[i].frame,to:preferred.frame,beat_id:preferred.id,
        time_seconds:preferred.time_seconds,drift_seconds:preferred.drift_seconds});
      previous=preferred.frame;assigned++;
      available.splice(available.indexOf(preferred),1);
    }
    // A shortfall or collision must never generate a partial, silently staged proposal.
    if(assigned!==movable.length){
      return {ok:false,moves:[],tracks:clone(tracks),warnings};
    }
    result.positive.keyframes.sort((a,b)=>a.frame-b.frame);
    const frames=result.positive.keyframes.map(x=>x.frame);
    if(new Set(frames).size!==frames.length||
       frames.some((f,i)=>i>0&&f<=frames[i-1])){
      return {ok:false,moves:[],tracks:clone(tracks),
        warnings:[...warnings,'Proposed positions collide with an existing locked scene.']};
    }
    return {ok:true,moves,tracks:result,warnings};
  }
  function mount({panel,getDraft,getLockedFrames}={}){
    if(!panel||!getDraft)throw Error('PS6.1 needs Prompt Studio and a draft supplier.');
    panel.innerHTML=[
      '<div class="ps61-head"><div><h3>PS6.1 · Audio beat-to-scene preview</h3>',
      '<p class="muted">Inspect a WAV already analyzed in Motion Studio. Saved manual',
      ' marker edits take priority over detected beats. This step previews frame placement',
      ' only. No audio, prompt, camera motion or project files are changed.</p></div></div>',
      '<div class="ps61-controls">',
      '<label>Project-owned analyzed WAV<select data-a6="wav"></select></label>',
      '<button type="button" class="secondary-button compact" data-a6="refresh">Refresh WAVs</button>',
      '<button type="button" class="primary-button compact" data-a6="load">Load Beats</button>',
      '</div>',
      '<p class="ps61-status" data-a6="status" role="status" aria-live="polite">',
      'Import a project draft and analyze a WAV in Motion Studio to begin.</p>',
      '<div data-a6="loaded" hidden>',
      '<p data-a6="identity" class="muted"></p>',
      '<div class="ps61-controls">',
      '<label>Marker type<select data-a6="kind"><option value="all">All types</option>',
      '<option value="kick">Kick</option><option value="snare">Snare</option>',
      '<option value="highs">Highs</option></select></label>',
      '<label>From (s)<input data-a6="from" type="number" min="0" step=".1" value="0"></label>',
      '<label>To (s)<input data-a6="to" type="number" min="0" step=".1"></label>',
      '<button type="button" class="secondary-button compact" data-a6="select">Select Visible Beats</button>',
      '<button type="button" class="secondary-button compact" data-a6="clear">Clear Selection</button>',
      '</div>',
      '<div data-a6="warnings" class="ps61-warnings"></div>',
      '<div data-a6="lane" class="ps61-beat-lane" aria-label="Beat selection timeline"></div>',
      '<div data-a6="markers" class="ps61-markers" role="group" aria-label="Selectable audio beats"></div>',
      '<p data-a6="count" class="muted"></p>',
      '<h4>Scene placement and locks</h4>',
      '<p class="muted">Frame 0 stays fixed. Lock any other positive prompt scene to keep',
      ' its original frame. The negative prompt track is never moved.</p>',
      '<div data-a6="locks" class="ps61-locks"></div>',
      '<div class="ps4-actions"><button type="button" class="secondary-button compact"',
      ' data-a6="plan">Preview Beat Alignment</button>',
      '<button type="button" class="secondary-button compact" data-a6="discard">Discard Preview</button></div>',
      '<section data-a6="review" class="ps61-review" hidden>',
      '<h4>Proposed scene positions (read-only)</h4><p class="muted"',
      ' data-a6="review-note"></p><div data-a6="diff"></div>',
      '<p class="muted">PS6.1 does not apply or save positions. PS6.2 will introduce',
      ' confirmation-gated, revision-safe staging after preview acceptance.</p>',
      '</section></div>'
    ].join('');
    const q=k=>panel.querySelector('[data-a6="'+k+'"]');
    let items=[],source=null,events=null,signature='',project='',loading=false,requestId=0;
    const selection=new Set(),locks=new Set();
    function status(s,error=false){q('status').textContent=s;q('status').dataset.error=error?'1':'0';}
    function discard(){q('review').hidden=true;q('diff').replaceChildren();}
    function reset(){
      ++requestId;project='';source=null;events=null;items=[];signature='';
      selection.clear();locks.clear();q('wav').replaceChildren();
      q('loaded').hidden=true;discard();
      status('Choose a project and a Motion Studio analyzed WAV.');refresh();
    }
    function refresh(){
      const d=getDraft(),id=d?.snapshot?.projectId||'';
      if(project&&project!==id){reset();return;}
      if(!d?.ok||d.applied){q('loaded').hidden=true;return;}
      q('load').disabled=loading||!q('wav').value;
      q('refresh').disabled=loading;
      if(events&&source&&signature!==contextSignature(d)){
        selection.clear();events=null;discard();q('loaded').hidden=true;
        status('Studio FPS, frame count or project changed; reload beats before preview.');
      }
    }
    const endpoint=id=>'/api/animation/projects/'+encodeURIComponent(id);
    const contextSignature=d=>d.snapshot.projectId+'|'+d.snapshot.context.fps+'|'+
      d.snapshot.context.maxFrames;
    async function json(url){
      const response=await fetch(url,{cache:'no-store'});
      const data=await response.json().catch(()=>null);
      if(!response.ok||!data)throw Error(data?.detail||'Read-only Motion Studio API HTTP '+response.status);
      return data;
    }
    async function refreshList(){
      const d=getDraft();if(!d?.ok||loading)return;
      const id=d.snapshot.projectId,token=++requestId;
      loading=true;refresh();status('Reading saved project WAV inventory…');
      try{
        const inventory=await json(endpoint(id)+'/media-inventory');
        if(token!==requestId||getDraft()!==d)return;
        items=(inventory.assets||[]).filter(a=>a.kind==='motion_lab_wav'&&
          a.project_id===id&&DIGEST.test(a.sha256||'')&&
          a.media_type==='audio/wav');
        const prior=q('wav').value;q('wav').replaceChildren();
        for(const a of items){
          const o=document.createElement('option');o.value=a.sha256;
          o.textContent=a.filename+' · '+Math.round(a.bytes/1024)+' KiB';
          q('wav').appendChild(o);
        }
        if(items.some(x=>x.sha256===prior))q('wav').value=prior;
        status(items.length?items.length+' analyzed project WAV(s) found. Select one and Load Beats.':
          'No analyzed WAV found. Use Motion Studio → Load/Analyze WAV, then Refresh WAVs.');
        if(source&&!items.some(a=>a.sha256===source.sha256)){
          source=null;events=null;selection.clear();q('loaded').hidden=true;discard();
        }
      }catch(error){if(token===requestId)status(error.message,true);}
      finally{if(token===requestId){loading=false;refresh();}}
    }
    async function load(){
      const d=getDraft(),id=d?.snapshot?.projectId,sha=q('wav').value;
      if(!d?.ok||loading||!items.some(a=>a.sha256===sha))return;
      const token=++requestId;
      loading=true;refresh();status('Loading verified WAV events and saved Motion Studio marker edits…');
      q('loaded').hidden=true;discard();
      try{
        const [a,m]=await Promise.all([
          json(endpoint(id)+'/motion-lab/audio/'+sha+'/analysis'),
          json(endpoint(id)+'/motion-lab/audio-markers/'+sha)
        ]);
        if(token!==requestId||getDraft()!==d)return;
        if(a.analysis?.source_sha256!==sha||
           (m.markers&&m.markers.source_sha256!==sha))
          throw Error('Audio source identity changed during loading.');
        const analysis=a.analysis,marked=m.markers;
        const duration=Number(analysis.duration_seconds);
        if(marked&&Math.abs(marked.duration_seconds-duration)>.02)
          throw Error('Saved markers have a different duration from this verified WAV.');
        const e=normalizeEvents(marked?marked.events:analysis.events?.events,
          duration,Number(d.snapshot.context.fps),
          Number(d.snapshot.context.maxFrames),{saved:Boolean(marked)});
        source={sha256:sha,duration,project_id:id,
          marker_mode:marked?'saved-edits':'detected',
          analysis_version:analysis.events?.analysis_version||null};
        events=e;signature=contextSignature(d);project=id;
        selection.clear();locks.clear();
        q('to').value=Math.min(duration,d.snapshot.context.maxFrames/d.snapshot.context.fps).toFixed(3);
        q('loaded').hidden=false;render();
        status(e.points.length+' '+(marked?'saved':'detected')+' markers ready. No prompt edits were made.');
      }catch(error){if(token===requestId)status(error.message,true);}
      finally{if(token===requestId){loading=false;refresh();}}
    }
    function filtered(){
      if(!events||!source)return [];
      const kind=q('kind').value;
      const from=Number(q('from').value),to=Number(q('to').value);
      if(!Number.isFinite(from)||!Number.isFinite(to)||from<0||to<=from)return [];
      return events.points.filter(e=>e.enabled&&e.time_seconds>=from&&
        e.time_seconds<to&&(kind==='all'||e.kind===kind));
    }
    function render(){
      if(!events||!source)return;
      discard();
      const d=getDraft();
      q('identity').textContent='Verified project WAV '+source.sha256.slice(0,12)+
        '… · '+source.duration.toFixed(3)+'s · '+source.marker_mode+
        ' · project '+d.snapshot.context.fps+' FPS / '+d.snapshot.context.maxFrames+
        ' frames. Source timestamps map to nearest frame; out-of-range markers are rejected.';
      const warn=q('warnings');warn.replaceChildren();
      for(const message of events.warnings){
        const p=document.createElement('p');p.textContent=message;warn.appendChild(p);
      }
      const all=filtered(),limited=all.slice(0,120);
      const el=q('markers'),lane=q('lane');el.replaceChildren();lane.replaceChildren();
      const duration=d.snapshot.context.maxFrames/d.snapshot.context.fps;
      for(const p of limited){
        const row=document.createElement('label');row.className='ps61-marker';
        const check=document.createElement('input');check.type='checkbox';
        check.checked=selection.has(p.id);check.disabled=p.frame===null||p.frame===0;
        check.addEventListener('change',()=>{
          if(check.checked)selection.add(p.id);else selection.delete(p.id);
          discard();render();
        });
        const label=document.createElement('span');
        label.textContent=p.kind+' · '+p.time_seconds.toFixed(3)+'s → '+
          (p.frame===null?'outside animation':'F'+p.frame+' (drift '+(p.drift_seconds*1000).toFixed(1)+'ms)');
        row.append(check,label);el.appendChild(row);
        if(p.frame!==null&&p.frame>0){
          const button=document.createElement('button');
          button.type='button';button.className='ps61-tick';
          button.style.left=Math.min(99.5,Math.max(.5,p.time_seconds/duration*100))+'%';
          button.title=p.kind+' · frame '+p.frame;
          button.setAttribute('aria-label','Toggle '+p.kind+' beat at frame '+p.frame);
          button.dataset.selected=selection.has(p.id)?'1':'0';
          button.addEventListener('click',()=>{
            if(selection.has(p.id))selection.delete(p.id);else selection.add(p.id);
            discard();render();
          });lane.appendChild(button);
        }
      }
      q('count').textContent=all.length+' matching enabled markers · '+limited.length+
        ' displayed (up to 120 in this range) · '+selection.size+' selected for preview.';
      const lockBox=q('locks');lockBox.replaceChildren();
      for(const p of d.tracks.positive.keyframes){
        const row=document.createElement('label');row.className='ps61-lock';
        const input=document.createElement('input');input.type='checkbox';
        input.checked=p.frame===0||locks.has(p.frame);
        input.disabled=p.frame===0;
        input.addEventListener('change',()=>{
          if(input.checked)locks.add(p.frame);else locks.delete(p.frame);
          discard();
        });
        row.append(input,document.createTextNode('Keep frame '+p.frame+
          (p.frame===0?' (always fixed)':'')+' · '+p.value.slice(0,65)));
        lockBox.appendChild(row);
      }
    }
    function preview(){
      if(!events||!source)return;
      const d=getDraft();
      if(!d?.ok||d.applied||signature!==contextSignature(d)||
         source.project_id!==d.snapshot.projectId){
        discard();return status('Audio mapping became stale. Reload beats.',true);
      }
      if(getLockedFrames?.().has('positive')){
        discard();return status('Positive lane is locked in the Visual Prompt Timeline. Unlock it to preview movement.',true);
      }
      const current=filtered();
      const proposed=planAlignment(d.tracks,current,selection,locks,
        d.snapshot.context.maxFrames);
      const diff=q('diff');diff.replaceChildren();q('review').hidden=false;
      for(const message of proposed.warnings){
        const p=document.createElement('p');p.className='ps61-warning';p.textContent=message;diff.appendChild(p);
      }
      for(const move of proposed.moves){
        const p=document.createElement('p');
        p.textContent='Scene F'+move.from+' → F'+move.to+' · '+move.beat_id+
          ' at '+move.time_seconds.toFixed(3)+'s (drift '+
          (move.drift_seconds*1000).toFixed(1)+'ms)';
        diff.appendChild(p);
      }
      q('review-note').textContent=proposed.ok?
        proposed.moves.length+' positive scene(s) would move. Frame 0, locked scenes, negative prompts and every prompt character remain intact.':
        'No safe complete alignment for this selection. Adjust beat selection, locks or project length.';
      status(proposed.ok?'Read-only alignment preview ready. No project or draft changes.':
        'Alignment preview blocked by collisions or insufficient beats.',!proposed.ok);
    }
    q('refresh').addEventListener('click',()=>void refreshList());
    q('load').addEventListener('click',()=>void load());
    q('kind').addEventListener('change',render);
    for(const key of ['from','to'])q(key).addEventListener('change',render);
    q('wav').addEventListener('change',()=>{
      source=null;events=null;selection.clear();q('loaded').hidden=true;discard();
    });
    q('select').addEventListener('click',()=>{
      for(const p of filtered().slice(0,120))
        if(p.frame!==null&&p.frame>0)selection.add(p.id);
      render();
    });
    q('clear').addEventListener('click',()=>{selection.clear();render();});
    q('plan').addEventListener('click',preview);
    q('discard').addEventListener('click',discard);
    refresh();
    return {refresh,reset,refreshList};
  }
  const api={frameAt,normalizeEvents,planAlignment,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioAudio=api;
})(typeof window==='object'?window:null);
