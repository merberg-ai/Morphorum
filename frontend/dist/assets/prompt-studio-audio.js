/* PS6.2: project-owned beat alignment with consent, source freshness and undoable staging. */
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
       !Array.isArray(events)||!(selectedIds instanceof Set)||
       !(lockedFrames instanceof Set)||!Number.isInteger(maxFrames)||maxFrames<1)
      throw Error('Valid tracks, markers, frame count and a lock set are required.');
    const result=clone(tracks),moves=[],warnings=[];
    const anchors=result.positive.keyframes;
    const selected=events.filter(e=>selectedIds.has(e.id)&&e.enabled&&
      Number.isInteger(e.frame)&&e.frame>0&&e.frame<maxFrames)
      .sort((a,b)=>a.frame-b.frame||a.time_seconds-b.time_seconds||a.id.localeCompare(b.id));
    const unique=new Map();
    for(const event of selected)if(!unique.has(event.frame))unique.set(event.frame,event);
    if(selected.length!==unique.size)
      warnings.push('Selected beats sharing one frame are reduced to one candidate.');
    const protectedFrames=new Set([0,...lockedFrames]);
    const checkpoints=anchors.map((p,i)=>({...p,index:i,
      locked:i===0||protectedFrames.has(p.frame)}));
    let boundary=0;
    for(let i=1;i<=checkpoints.length;i++){
      if(i<checkpoints.length&&!checkpoints[i].locked)continue;
      const end=i===checkpoints.length?maxFrames:checkpoints[i].frame;
      const movable=checkpoints.slice(boundary+1,i);
      let candidates=[...unique.values()].filter(e=>
        e.frame>checkpoints[boundary].frame&&e.frame<end);
      if(candidates.length<movable.length){
        if(movable.length)warnings.push('Not enough distinct beats between protected scenes F'+
          checkpoints[boundary].frame+' and '+(end===maxFrames?'end':'F'+end)+'.');
        return {ok:false,moves:[],tracks:clone(tracks),warnings};
      }
      let prior=checkpoints[boundary].frame;
      for(let j=0;j<movable.length;j++){
        const original=movable[j],left=movable.length-j-1;
        const valid=candidates.filter(e=>e.frame>prior);
        const choices=valid.slice(0,Math.max(0,valid.length-left));
        if(!choices.length)return {ok:false,moves:[],tracks:clone(tracks),
          warnings:[...warnings,'No chronological marker space remains.']};
        const chosen=choices.reduce((a,b)=>
          Math.abs(a.frame-original.frame)<=Math.abs(b.frame-original.frame)?a:b);
        result.positive.keyframes[original.index].frame=chosen.frame;
        if(chosen.frame!==original.frame)
          moves.push({from:original.frame,to:chosen.frame,beat_id:chosen.id,
            time_seconds:chosen.time_seconds,drift_seconds:chosen.drift_seconds});
        prior=chosen.frame;
        candidates=valid.filter(e=>e.frame>prior);
      }
      boundary=i;
    }
    result.positive.keyframes.sort((a,b)=>a.frame-b.frame);
    const frames=result.positive.keyframes.map(x=>x.frame);
    if(new Set(frames).size!==frames.length||
       frames.some((x,i)=>i>0&&x<=frames[i-1]))
      return {ok:false,moves:[],tracks:clone(tracks),
        warnings:[...warnings,'Beat positions would reorder or collide with a protected scene.']};
    if(!moves.length)warnings.push('Selected beats would not move any unlocked scene.');
    return {ok:!!moves.length,moves,tracks:result,warnings};
  }
  function mount({panel,getDraft,getLockedFrames,onStage,onUndo,onRedo}={}){
    if(!panel||!getDraft)throw Error('PS6.1 needs Prompt Studio and a draft supplier.');
    panel.innerHTML=[
      '<div class="ps61-head"><div><h3>PS6.2 · Audio beat-to-scene synchronization</h3>',
      '<p class="muted">Import an analyzed project WAV and review the exact beat-to-frame',
      ' mapping. Saved manual marker edits take priority over detected beats. Staging',
      ' requires fresh source verification and confirmation. No soundtrack or camera',
      ' schedules are overwritten.</p></div></div>',
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
      '<h4>Proposed scene positions</h4><p class="muted"',
      ' data-a6="review-note"></p><div data-a6="diff"></div>',
      '<div class="ps4-actions"><button type="button" class="primary-button compact"',
      ' data-a6="stage" disabled>Stage Alignment in Studio Draft</button></div>',
      '<p class="muted">Stage changes only the editable Prompt Studio positive lane.',
      ' Use Undo / Redo below, then Preview Changes → Apply to Animation → Save Project.',
      ' The actual render is a separate action.</p></section>',
      '<div class="ps4-actions">',
      '<button type="button" class="secondary-button compact" data-a6="undo">',
      'Undo Studio Change</button>',
      '<button type="button" class="secondary-button compact" data-a6="redo">',
      'Redo Studio Change</button></div></div>'
    ].join('');
    const q=k=>panel.querySelector('[data-a6="'+k+'"]');
    let items=[],source=null,events=null,signature='',project='',loading=false,requestId=0;
    let pending=null,staging=false;
    const selection=new Set(),locks=new Set();
    function status(s,error=false){q('status').textContent=s;q('status').dataset.error=error?'1':'0';}
    function discard(){
      pending=null;q('review').hidden=true;q('diff').replaceChildren();
      q('stage').disabled=true;
    }
    function invalidate(){discard();locks.clear();if(events)render();}
    function reset(){
      ++requestId;project='';source=null;events=null;items=[];signature='';staging=false;
      selection.clear();locks.clear();q('wav').replaceChildren();
      q('loaded').hidden=true;discard();
      status('Choose a project and a Motion Studio analyzed WAV.');refresh();
    }
    function refresh(){
      const d=getDraft(),id=d?.snapshot?.projectId||'';
      if(project&&project!==id){reset();return;}
      if(!d?.ok||d.applied){q('loaded').hidden=true;return;}
      q('load').disabled=loading||staging||!q('wav').value;
      q('refresh').disabled=loading||staging;
      q('plan').disabled=loading||staging||!events;
      q('stage').disabled=staging||!pending;
      q('discard').disabled=staging;
      q('undo').disabled=staging;
      q('redo').disabled=staging;
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
        const [a,m,identity]=await Promise.all([
          json(endpoint(id)+'/motion-lab/audio/'+sha+'/analysis'),
          json(endpoint(id)+'/motion-lab/audio-markers/'+sha),
          json(endpoint(id)+'/prompt-studio/audio-context/'+sha)
        ]);
        if(token!==requestId||getDraft()!==d)return;
        if(a.analysis?.source_sha256!==sha||
           (m.markers&&m.markers.source_sha256!==sha)||
           identity.source_sha256!==sha||
           identity.project_id!==id||
           identity.fps!==Number(d.snapshot.context.fps)||
           identity.max_frames!==Number(d.snapshot.context.maxFrames)||
           identity.marker_mode!==(m.markers?'saved-edits':'detected'))
          throw Error('Audio source, markers or saved project timing changed. Reload Project Editor.');
        const analysis=a.analysis,marked=m.markers;
        const duration=Number(analysis.duration_seconds);
        if(marked&&Math.abs(marked.duration_seconds-duration)>.02)
          throw Error('Saved markers have a different duration from this verified WAV.');
        const e=normalizeEvents(marked?marked.events:analysis.events?.events,
          duration,Number(d.snapshot.context.fps),
          Number(d.snapshot.context.maxFrames),{saved:Boolean(marked)});
        source={sha256:sha,duration,project_id:id,
          marker_mode:marked?'saved-edits':'detected',
          stamp:identity.stamp,markers_sha256:identity.markers_sha256,
          soundtrack_sha256:identity.soundtrack_sha256,
          soundtrack_offset_seconds:identity.soundtrack_offset_seconds,
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
      const attachmentNote=source.soundtrack_sha256===null?
        'No attached export soundtrack yet. This preview uses a saved Motion Studio WAV.':
        source.soundtrack_sha256===source.sha256?
          'WAV matches attached project soundtrack.':
          'Attached soundtrack has a different checksum (e.g. converted compressed audio). Verify the WAV matches its content.';
      const offset=source.soundtrack_offset_seconds||0;
      q('identity').textContent='Verified project WAV '+source.sha256.slice(0,12)+
        '… · '+source.duration.toFixed(3)+'s · '+source.marker_mode+
        ' · '+d.snapshot.context.fps+' FPS / '+d.snapshot.context.maxFrames+
        ' frames. Source timestamps snap to nearest frame; out-of-range rejected. '+
        attachmentNote+(Math.abs(offset)>1e-6?
          ' Export audio offset '+offset.toFixed(3)+'s requires separate timing correction.':'');
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
        row.title='Lock positive scene at frame '+p.frame+' · '+p.value.slice(0,240);
        const input=document.createElement('input');input.type='checkbox';
        input.checked=p.frame===0||locks.has(p.frame);
        input.disabled=p.frame===0;
        input.addEventListener('change',()=>{
          if(input.checked)locks.add(p.frame);else locks.delete(p.frame);
          discard();
        });
        const summary=document.createElement('span');summary.className='ps61-lock-text';
        summary.textContent='Keep F'+p.frame+(p.frame===0?' (fixed)':'')+' · '+
          p.value.replace(/\s+/g,' ').slice(0,90);
        row.append(input,summary);lockBox.appendChild(row);
      }
    }
    function liveMatches(d,rev,original,token){
      return token===requestId&&getDraft()===d&&d?.ok&&!d.applied&&
        d.revision===rev&&JSON.stringify(d.tracks)===original&&
        source?.project_id===d.snapshot.projectId&&
        signature===contextSignature(d)&&
        !getLockedFrames?.().has('positive');
    }
    async function freshContext(id,sha,stamp){
      const fresh=await json(endpoint(id)+'/prompt-studio/audio-context/'+sha);
      if(fresh.project_id!==id||fresh.source_sha256!==sha||
         fresh.stamp!==stamp||fresh.marker_mode!==source?.marker_mode)
        throw Error('Saved WAV, markers, soundtrack/offset or project timing changed. Reload Beats and preview again.');
      return fresh;
    }
    async function preview(){
      if(!events||!source||loading||staging)return;
      const d=getDraft(),revision=d?.revision,token=requestId,
        original=JSON.stringify(d?.tracks);
      if(!d?.ok||d.applied||signature!==contextSignature(d)||
         source.project_id!==d.snapshot.projectId){
        discard();return status('Audio mapping became stale. Reload Beats.',true);
      }
      if(getLockedFrames?.().has('positive')){
        discard();return status('Positive lane is locked in the Visual Prompt Timeline.',true);
      }
      const chosen=filtered(),selected=new Set([...selection].filter(x=>chosen.some(y=>y.id===x)));
      if(!selected.size||selected.size>120){
        discard();return status('Select between 1 and 120 visible beats before previewing.',true);
      }
      const proposed=planAlignment(d.tracks,chosen,selected,locks,d.snapshot.context.maxFrames);
      discard();q('review').hidden=false;
      const diff=q('diff');
      for(const message of proposed.warnings){
        const p=document.createElement('p');p.className='ps61-warning';
        p.textContent=message;diff.appendChild(p);
      }
      for(const move of proposed.moves){
        const p=document.createElement('p');p.className='ps61-move';
        p.textContent='Scene F'+move.from+' → F'+move.to+' · '+move.beat_id+
          ' at '+move.time_seconds.toFixed(3)+'s (drift '+
          (move.drift_seconds*1000).toFixed(1)+'ms)';
        diff.appendChild(p);
      }
      q('review-note').textContent=proposed.ok?
        proposed.moves.length+' scene(s) will move. Frame 0, locked scenes, negative lane and all LoRA/prompt bytes stay intact. Verification in progress…':
        'No complete safe alignment. Change the beat selection or locks.';
      if(!proposed.ok)return status('Alignment preview blocked. No changes made.',true);
      status('Verifying source WAV, saved markers and project timing…');
      try{
        const identity=await freshContext(d.snapshot.projectId,source.sha256,source.stamp);
        if(!liveMatches(d,revision,original,token)){
          discard();return status('Draft or audio selection changed while verifying. Preview again.',true);
        }
        pending={draft:d,revision,original,token,tracks:proposed.tracks,
          moves:proposed.moves,selectedIds:[...selected],identity};
        q('review-note').textContent=proposed.moves.length+
          ' safe scene movement(s). Source confirmed current. Confirm staging separately.';
        q('stage').disabled=false;
        status('Preview verified. Review movements before staging.');
      }catch(error){
        discard();status('Source verification failed: '+(error.message||error),true);
      }
    }
    async function stage(){
      const p=pending,d=getDraft();
      if(!p||staging||loading||!liveMatches(d,p.revision,p.original,p.token)||
         p!==pending)return status('Preview is stale. Re-run Preview Beat Alignment.',true);
      if(source.soundtrack_offset_seconds!==null&&
         Math.abs(source.soundtrack_offset_seconds)>1e-6)
        return status('Attached soundtrack has a nonzero export offset. Raw beat frames '+
          'would not align with exported audio. Set offset to 0 or use the upcoming '+
          'offset-aware sync before staging.',true);
      if(!root.MorphorumDialog?.confirm)
        return status('Confirmation dialog unavailable. No scenes were moved.',true);
      staging=true;refresh();
      try{
        await freshContext(d.snapshot.projectId,source.sha256,p.identity.stamp);
        if(p!==pending||!liveMatches(d,p.revision,p.original,p.token))
          throw Error('Draft or project changed before confirmation.');
        const ok=await root.MorphorumDialog.confirm({
          title:'Stage audio-aligned scene positions?',
          message:'Move '+p.moves.length+' positive scene(s) to the previewed beat frames? '+
            'Original prompt/LoRA text, negative prompts, soundtrack and camera motion remain unchanged. '+
            'This only changes the unsaved Studio draft and can be undone in the Visual Prompt Timeline.',
          confirmText:'Stage Alignment',cancelText:'Keep Preview'});
        if(!ok){status('Staging cancelled. Preview remains unchanged.');return;}
        // Repeat the server check after the asynchronous user confirmation.
        await freshContext(d.snapshot.projectId,source.sha256,p.identity.stamp);
        if(p!==pending||!liveMatches(d,p.revision,p.original,p.token))
          throw Error('Audio or Studio revision changed while confirming. No prompts moved.');
        const stamp={
          schema_version:1,source_sha256:source.sha256,stamp:p.identity.stamp,
          fps:p.identity.fps,max_frames:p.identity.max_frames,
          marker_mode:p.identity.marker_mode,selected_event_ids:p.selectedIds,
          moves:p.moves.map(x=>({from:x.from,to:x.to,beat_id:x.beat_id})),
          staged_at:new Date().toISOString(),
        };
        const result=onStage?.(p.tracks,stamp);
        if(!result?.ok)throw Error(result?.message||'Studio refused the alignment.');
        discard();
        status('Beat alignment staged in Studio draft. Undo/Redo in the Visual Timeline, '+
          'or Preview Changes → Apply to Animation → Save Project.');
      }catch(error){
        discard();status('Staging blocked: '+(error.message||error),true);
      }finally{staging=false;refresh();}
    }
    async function verifyStaged(provenance){
      if(!provenance)return true;
      const d=getDraft();
      if(!d?.ok||d.applied||!d.snapshot?.projectId)
        throw Error('No editable project for audio alignment.');
      // This also works after a browser reload with no PS6 audio preview open.
      const stamp=await json(endpoint(d.snapshot.projectId)+
        '/prompt-studio/audio-context/'+encodeURIComponent(provenance.source_sha256));
      if(stamp.stamp!==provenance.stamp||stamp.fps!==provenance.fps||
         stamp.max_frames!==provenance.max_frames)
        throw Error('Staged beat alignment is stale: WAV, markers, soundtrack, offset or project timing changed. Undo/reload beats and stage again.');
      return true;
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
    q('plan').addEventListener('click',()=>void preview());
    q('stage').addEventListener('click',()=>void stage());
    q('undo').addEventListener('click',()=>{
      const result=onUndo?.();
      status(result?'Undid last Studio change.':'No Studio change to undo.');
    });
    q('redo').addEventListener('click',()=>{
      const result=onRedo?.();
      status(result?'Redid last Studio change.':'No Studio change to redo.');
    });
    q('discard').addEventListener('click',discard);
    refresh();
    return {refresh,reset,refreshList,invalidate,verifyStaged};
  }
  const api={frameAt,normalizeEvents,planAlignment,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioAudio=api;
})(typeof window==='object'?window:null);
