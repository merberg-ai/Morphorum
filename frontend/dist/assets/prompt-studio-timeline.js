/* PS2 native prompt timeline: frame math, atomic lane edits, reversible history and touch UI. */
(function(root){
  'use strict';
  const copy=value=>JSON.parse(JSON.stringify(value));
  const error=(code,message)=>({ok:false,code,message});
  const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
  function snapFrame(value,step,maxFrames){
    if(!Number.isFinite(value)||!Number.isInteger(maxFrames)||maxFrames<1) return 0;
    const interval=Math.max(1,Math.trunc(Number(step)||1));
    return clamp(Math.round(Math.round(value)/interval)*interval,0,maxFrames-1);
  }
  function pixelGeometry(frames,zoom){
    const maxFrames=Math.max(1,Math.trunc(Number(frames)||1));
    const px=Math.max(.5,Math.min(32,Number(zoom)||4));
    const width=Math.min(150000,Math.max(660,(maxFrames-1)*px+56));
    const range=Math.max(1,width-48);
    return {width,px:range/Math.max(1,maxFrames-1),start:24,
      frameToX:frame=>24+clamp(Number(frame)||0,0,maxFrames-1)*range/Math.max(1,maxFrames-1),
      xToFrame:x=>clamp(Math.round((x-24)*Math.max(1,maxFrames-1)/range),0,maxFrames-1)};
  }
  function previewShift(tracks,selection,delta,maxFrames,locked=[]){
    if(!Number.isInteger(delta))return error('DELTA','Invalid shift distance.');
    if(!Array.isArray(selection)||!selection.length)return error('SELECTION','Select a keyframe first.');
    const next=copy(tracks),moves=[];
    const selections=new Set(selection.map(s=>s.lane+':'+s.frame));
    for(const item of selection){
      if(!['positive','negative'].includes(item.lane)||locked.includes(item.lane))
        return error('LOCKED','Unlock the selected prompt lane first.');
      const source=next[item.lane].keyframes.find(p=>p.frame===item.frame);
      if(!source)return error('MISSING','A selected keyframe no longer exists.');
      if(item.frame===0)return error('FRAME_ZERO','Frame zero is anchored and cannot move.');
      const target=item.frame+delta;
      if(target<=0||target>=maxFrames)return error('RANGE','Shift would move a keyframe outside the timeline.');
      const occupied=next[item.lane].keyframes.some(p=>p.frame===target&&!selections.has(item.lane+':'+p.frame));
      if(occupied)return error('COLLISION','Destination collides with another keyframe in '+item.lane+'.');
      moves.push({lane:item.lane,from:item.frame,to:target});
    }
    for(const move of moves){
      const point=next[move.lane].keyframes.find(p=>p.frame===move.from);
      point.frame=move.to;
    }
    for(const lane of ['positive','negative'])
      next[lane].keyframes.sort((a,b)=>a.frame-b.frame);
    return {ok:true,tracks:next,selection:moves.map(m=>({lane:m.lane,frame:m.to}))};
  }
  function duplicateSelection(tracks,selection,step,maxFrames,locked=[]){
    if(!Array.isArray(selection)||!selection.length)return error('SELECTION','Select keyframes to duplicate.');
    const source=selection.filter(s=>s.frame!==0);
    if(!source.length)return error('FRAME_ZERO','Select nonzero keyframes to duplicate.');
    const increment=Math.max(1,Math.trunc(Number(step)||1));
    const next=copy(tracks);
    const additions=[];
    for(const {lane,frame} of source){
      if(!['positive','negative'].includes(lane)||locked.includes(lane))
        return error('LOCKED','Unlock the selected prompt lane first.');
      const key=next[lane].keyframes.find(x=>x.frame===frame);
      if(!key)return error('MISSING','Selected keyframe is missing.');
      const destination=frame+increment;
      if(destination>=maxFrames)return error('RANGE','Duplicate destination is past the last frame.');
      if(next[lane].keyframes.some(p=>p.frame===destination)||
          additions.some(p=>p.lane===lane&&p.frame===destination))
        return error('COLLISION','A duplicate destination is occupied.');
      additions.push({lane,frame:destination,value:key.value});
    }
    for(const key of additions) next[key.lane].keyframes.push({frame:key.frame,value:key.value});
    for(const lane of ['positive','negative'])next[lane].keyframes.sort((a,b)=>a.frame-b.frame);
    return {ok:true,tracks:next,selection:additions.map(p=>({lane:p.lane,frame:p.frame}))};
  }
  function deleteSelection(tracks,selection,locked=[]){
    if(!Array.isArray(selection)||!selection.length)
      return error('SELECTION','Select keyframes to delete.');
    const next=copy(tracks),unique=new Set();
    for(const {lane,frame} of selection){
      if(!['positive','negative'].includes(lane)||locked.includes(lane))
        return error('LOCKED','Unlock the selected prompt lanes before deleting.');
      if(frame===0)return error('FRAME_ZERO','Frame zero cannot be deleted.');
      if(!next[lane].keyframes.some(p=>p.frame===frame))
        return error('MISSING','A selected keyframe is missing.');
      unique.add(lane+':'+frame);
    }
    for(const lane of ['positive','negative'])
      next[lane].keyframes=next[lane].keyframes.filter(p=>!unique.has(lane+':'+p.frame));
    return {ok:true,tracks:next,selection:[]};
  }
  function sceneSegments(tracks,maxFrames,fps=24){
    const points=tracks.positive.keyframes;
    return points.map((item,i)=>{
      const next=points[i+1]?.frame ?? maxFrames;
      return {index:i+1,start:item.frame,end:next-1,frames:next-item.frame,
        seconds:(next-item.frame)/fps,value:item.value};
    });
  }
  function evenlySpace(tracks,lane,maxFrames,locked=[]){
    if(!['positive','negative'].includes(lane)||locked.includes(lane))
      return error('LOCKED','Unlock the selected prompt lane first.');
    const next=copy(tracks),keys=next[lane].keyframes;
    if(keys.length>maxFrames)return error('CAPACITY','More keyframes than available frames.');
    if(keys.length<=1)return {ok:true,tracks:next};
    for(let i=0;i<keys.length;i++)keys[i].frame=Math.round(i*(maxFrames-1)/(keys.length-1));
    return {ok:true,tracks:next};
  }
  function createHistory(limit=80){
    const undo=[],redo=[];let group='',last=0;
    return {
      record(before,key='edit'){
        const now=Date.now();
        const merge=key.startsWith('text:')&&group===key&&now-last<850;
        if(!merge){undo.push(copy(before));if(undo.length>limit)undo.shift();}
        redo.length=0;group=key;last=now;
      },
      undo(current){
        if(!undo.length)return null;
        const previous=undo.pop();redo.push(copy(current));group='';return previous;
      },
      redo(current){
        if(!redo.length)return null;
        const next=redo.pop();undo.push(copy(current));group='';return next;
      },
      reset(){undo.length=0;redo.length=0;group='';last=0;},
      get canUndo(){return undo.length>0;},
      get canRedo(){return redo.length>0;},
    };
  }
  function mount({panel,getDraft,onEdit,onTracks,onNotice}={}){
    if(!panel)throw new Error('Timeline container is required.');
    const history=createHistory();
    const state={zoom:4,snap:1,frame:0,selection:[],locks:new Set(),drag:null,
      seq:0,inspecting:false};
    panel.innerHTML=`
      <div class="ps2-header"><div><h3>Visual Prompt Timeline</h3>
        <p class="muted">Drag a diamond to move a keyframe. Shift-click to select multiple. Locked lanes cannot be moved or edited.</p></div>
        <div class="ps2-tools">
          <label>Snap <select data-ps2="snap"><option value="1">1 frame</option><option value="2">2 frames</option><option value="5">5 frames</option><option value="10">10 frames</option><option value="24">24 frames</option></select></label>
          <label>Zoom <input data-ps2="zoom" type="range" min="1" max="24" value="4" step="1"></label>
          <button type="button" class="secondary-button compact" data-ps2="undo" title="Undo (Ctrl+Z)">Undo</button>
          <button type="button" class="secondary-button compact" data-ps2="redo" title="Redo (Ctrl+Shift+Z)">Redo</button>
          <button type="button" class="secondary-button compact" data-ps2="duplicate">Duplicate</button>
          <button type="button" class="secondary-button compact" data-ps2="delete">Delete Selected</button>
          <button type="button" class="secondary-button compact" data-ps2="space">Evenly Space</button>
        </div>
      </div>
      <div class="ps2-timeline-scroll" data-ps2="scroll" tabindex="0" aria-label="Scrollable prompt keyframe timeline">
        <div data-ps2="canvas" class="ps2-canvas">
          <div data-ps2="ruler" class="ps2-ruler" aria-label="Time ruler"></div>
          <div data-ps2="positive" class="ps2-track" aria-label="Positive prompt keyframes"></div>
          <div data-ps2="negative" class="ps2-track" aria-label="Negative prompt keyframes"></div>
          <div data-ps2="scenes" class="ps2-scenes" aria-label="Positive prompt scene durations"></div>
          <div data-ps2="playhead" class="ps2-playhead" aria-hidden="true"></div>
        </div>
      </div>
      <div class="ps2-footer">
        <label>Frame <input data-ps2="frame" type="number" min="0" value="0"></label>
        <input data-ps2="scrub" type="range" min="0" value="0" aria-label="Scrub animation frame">
        <output data-ps2="time">F0 · 0.00s</output>
        <span class="muted" data-ps2="selection">No keyframes selected</span>
      </div>
      <div class="ps2-inspector" aria-label="Resolved prompt frame inspector">
        <strong>Prompt inspector</strong>
        <p class="muted">Uses the native backend Hold/Blend prompt resolver. This is prompt-only, not a GPU render or model/LoRA inference preview.</p>
        <div data-ps2="inspector" role="status" aria-live="polite">Select or scrub a frame.</div>
      </div>`;
    const find=n=>panel.querySelector('[data-ps2="'+n+'"]');
    const scrub=find('scrub'),frameInput=find('frame'),scroll=find('scroll'),canvas=find('canvas');
    const displaySelection=()=>{
      const selected=state.selection;
      find('selection').textContent=selected.length?selected.length+' keyframe(s) selected':'No keyframes selected';
      find('undo').disabled=!history.canUndo;
      find('redo').disabled=!history.canRedo;
      const available=Boolean(getDraft()?.ok&&!getDraft().applied);
      find('duplicate').disabled=!available||!selected.length;
      find('delete').disabled=!available||!selected.length;
      find('space').disabled=!available||!selected.length;
    };
    function select(lane,frame,multi=false){
      const item={lane,frame};
      const exists=state.selection.some(x=>x.lane===lane&&x.frame===frame);
      if(multi){
        state.selection=exists?state.selection.filter(x=>!(x.lane===lane&&x.frame===frame)):
          [...state.selection,item];
      }else state.selection=[item];
      displaySelection();refresh();
    }
    function setFrame(frame,{scrollIntoView=false}={}){
      const draft=getDraft(),total=draft?.snapshot?.context?.maxFrames||1;
      state.frame=clamp(Math.round(Number(frame)||0),0,total-1);
      frameInput.value=String(state.frame);scrub.value=String(state.frame);
      const fps=Number(draft?.snapshot?.context?.fps)||24;
      find('time').textContent='F'+state.frame+' · '+(state.frame/fps).toFixed(2)+'s';
      const g=pixelGeometry(total,state.zoom);
      find('playhead').style.left=g.frameToX(state.frame)+'px';
      if(scrollIntoView){
        const x=g.frameToX(state.frame);
        if(x<scroll.scrollLeft+32||x>scroll.scrollLeft+scroll.clientWidth-32)
          scroll.scrollLeft=Math.max(0,x-scroll.clientWidth/2);
      }
      scheduleInspect();
    }
    let inspectTimer=null;
    function scheduleInspect(){
      root.clearTimeout(inspectTimer);
      inspectTimer=root.setTimeout(()=>void inspect(),140);
    }
    async function inspect(){
      const draft=getDraft();if(!draft?.ok)return;
      const seq=++state.seq,projectId=draft.snapshot.projectId;
      const output=find('inspector');
      output.textContent='Resolving prompts for frame '+state.frame+'…';
      try{
        const response=await fetch('/api/animation/projects/'+encodeURIComponent(projectId)+
          '/prompt-studio/inspect-frame',{method:'POST',cache:'no-store',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({frame:state.frame,max_frames:draft.snapshot.context.maxFrames,
            tracks:draft.tracks})});
        const body=await response.json();
        if(seq!==state.seq)return;
        if(!response.ok)throw new Error(body.detail||'Prompt inspection failed');
        output.replaceChildren();
        for(const lane of ['positive','negative']){
          const t=body[lane],section=document.createElement('div');
          section.className='ps2-inspector-lane';
          const heading=document.createElement('strong');
          heading.textContent=(lane==='positive'?'Positive':'Negative')+' · '+t.mode;
          section.appendChild(heading);
          const a=document.createElement('p');
          a.textContent='From F'+t.from_frame+' ('+Math.round(t.from_weight*100)+
            '%)'+(t.from_frame!==t.to_frame?' → F'+t.to_frame+' ('+
            Math.round(t.to_weight*100)+'%)':'');
          section.appendChild(a);
          const from=document.createElement('pre');from.textContent=t.from_text||'(empty)';
          section.appendChild(from);
          if(t.to_weight>0&&t.to_frame!==t.from_frame){
            const to=document.createElement('pre');to.textContent=t.to_text||'(empty)';
            section.appendChild(to);
          }
          output.appendChild(section);
        }
      }catch(err){if(seq===state.seq)output.textContent=err.message;}
    }
    function commitTracks(result,key='batch'){
      if(!result.ok){onNotice?.(result.message,true);return false;}
      const draft=getDraft();if(!draft?.ok||draft.applied)return false;
      if(JSON.stringify(draft.tracks)===JSON.stringify(result.tracks))return false;
      const before=copy(draft.tracks);
      const done=onTracks?.(result.tracks,key,before);
      if(!done?.ok){onNotice?.(done?.message||'Could not edit keyframes.',true);return false;}
      if(result.selection)state.selection=result.selection;
      refresh();return true;
    }
    function pointerDown(event,lane,frame,button,g){
      if(event.button!==undefined&&event.button!==0)return;
      const multi=event.shiftKey||event.ctrlKey||event.metaKey;
      if(!multi && !state.selection.some(x=>x.lane===lane&&x.frame===frame))
        state.selection=[{lane,frame}];
      else if(multi)select(lane,frame,true);
      displaySelection();
      const locked=state.locks.has(lane),invalid=state.selection.some(s=>s.frame===0||state.locks.has(s.lane));
      if(multi||locked||invalid||!getDraft()?.ok||getDraft().applied){
        refresh();return;
      }
      const origin=event.clientX;
      state.drag={pointerId:event.pointerId,origin,from:frame,lane,
        selection:copy(state.selection),geometry:g,delta:0,scrolled:scroll.scrollLeft};
      button.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    }
    function pointerMove(event,button){
      const drag=state.drag;if(!drag||drag.pointerId!==event.pointerId)return;
      const raw=Math.round((event.clientX-drag.origin+scroll.scrollLeft-drag.scrolled)/drag.geometry.px);
      const target=snapFrame(drag.from+raw,state.snap,getDraft().snapshot.context.maxFrames);
      const delta=target-drag.from;
      drag.delta=delta;
      const moved=previewShift(getDraft().tracks,drag.selection,delta,
        getDraft().snapshot.context.maxFrames,[...state.locks]);
      button.dataset.dragPreview=moved.ok?'F'+target:'Blocked';
      button.classList.toggle('ps2-invalid',!moved.ok);
      button.style.transform='translateX('+(moved.ok?delta*drag.geometry.px:0)+'px)';
    }
    function pointerEnd(event,button){
      const drag=state.drag;if(!drag||drag.pointerId!==event.pointerId)return;
      state.drag=null;button.style.transform='';delete button.dataset.dragPreview;
      button.classList.remove('ps2-invalid');
      if(drag.delta){
        commitTracks(previewShift(getDraft().tracks,drag.selection,drag.delta,
          getDraft().snapshot.context.maxFrames,[...state.locks]),'drag');
      }else refresh();
    }
    function refresh(){
      const draft=getDraft();
      const available=Boolean(draft?.ok&&!draft.applied);
      panel.hidden=!available;
      if(!available){state.seq+=1;return;}
      const total=draft.snapshot.context.maxFrames,fps=draft.snapshot.context.fps;
      const g=pixelGeometry(total,state.zoom);
      canvas.style.width=g.width+'px';frameInput.max=String(total-1);
      scrub.max=String(total-1);
      const ruler=find('ruler');ruler.replaceChildren();
      const interval=Math.max(1,Math.ceil(total/Math.min(90,Math.max(3,Math.floor(g.width/92)))));
      for(let frame=0;frame<total;frame+=interval){
        const tick=document.createElement('span');tick.className='ps2-tick';
        tick.style.left=g.frameToX(frame)+'px';
        tick.textContent='F'+frame+' · '+(frame/fps).toFixed(1)+'s';
        ruler.appendChild(tick);
      }
      for(const lane of ['positive','negative']){
        const row=find(lane);row.replaceChildren();
        row.dataset.lane=lane;
        row.classList.toggle('ps2-locked',state.locks.has(lane));
        const label=document.createElement('span');label.className='ps2-lane-label';
        label.textContent=lane==='positive'?'Positive':'Negative';
        row.appendChild(label);
        const lock=document.createElement('button');lock.type='button';
        lock.className='ps2-lock';lock.textContent=state.locks.has(lane)?'Locked':'Lock';
        lock.setAttribute('aria-label',(state.locks.has(lane)?'Unlock ':'Lock ')+lane+' lane');
        lock.addEventListener('click',()=>{state.locks.has(lane)?state.locks.delete(lane):state.locks.add(lane);
          refresh();onNotice?.(lane+' lane '+(state.locks.has(lane)?'locked':'unlocked')+'.');});
        row.appendChild(lock);
        for(const point of draft.tracks[lane].keyframes){
          const button=document.createElement('button');button.type='button';
          button.className='ps2-keyframe';
          button.style.left=g.frameToX(point.frame)+'px';
          button.dataset.lane=lane;button.dataset.frame=String(point.frame);
          button.dataset.psFixed=point.frame===0?'1':'0';
          const selected=state.selection.some(s=>s.lane===lane&&s.frame===point.frame);
          button.classList.toggle('selected',selected);
          button.classList.toggle('anchor',point.frame===0);
          button.title=(lane==='positive'?'Positive':'Negative')+' keyframe F'+point.frame;
          button.setAttribute('aria-label',button.title+
            (point.frame===0?' (anchored)':' (drag to move)'));
          button.addEventListener('pointerdown',event=>pointerDown(event,lane,point.frame,button,g));
          button.addEventListener('pointermove',event=>pointerMove(event,button));
          button.addEventListener('pointerup',event=>pointerEnd(event,button));
          button.addEventListener('pointercancel',event=>{state.drag=null;button.style.transform='';refresh();});
          button.addEventListener('click',event=>{
            if(event.detail===0)select(lane,point.frame,event.shiftKey||event.ctrlKey||event.metaKey);
            else if(!selected)select(lane,point.frame,event.shiftKey||event.ctrlKey||event.metaKey);
            setFrame(point.frame);
          });
          row.appendChild(button);
        }
      }
      const scenes=find('scenes');scenes.replaceChildren();
      for(const segment of sceneSegments(draft.tracks,total,fps)){
        const block=document.createElement('button');block.type='button';
        block.className='ps2-scene';
        block.style.left=g.frameToX(segment.start)+'px';
        block.style.width=Math.max(1,segment.frames*g.px-2)+'px';
        block.title='Scene '+segment.index+': frames '+segment.start+'–'+segment.end+
          ' · '+segment.seconds.toFixed(2)+' seconds';
        block.setAttribute('aria-label',block.title);
        block.textContent='Scene '+segment.index+' · '+segment.seconds.toFixed(1)+'s';
        block.addEventListener('click',()=>{setFrame(segment.start,{scrollIntoView:true});
          select('positive',segment.start);});
        scenes.appendChild(block);
      }
      state.selection=state.selection.filter(s=>draft.tracks[s.lane]?.keyframes.some(k=>k.frame===s.frame));
      displaySelection();
      setFrame(state.frame);
    }
    function restore(kind){
      const draft=getDraft();if(!draft?.ok||draft.applied)return;
      const prior=kind==='undo'?history.undo(draft.tracks):history.redo(draft.tracks);
      if(!prior)return;
      state.selection=[];const result=onTracks?.(prior,kind,null,true);
      if(!result?.ok){onNotice?.(result?.message||'Could not restore timeline',true);return;}
      refresh();
    }
    find('zoom').addEventListener('input',event=>{state.zoom=Number(event.target.value);refresh();});
    find('snap').addEventListener('change',event=>{state.snap=Number(event.target.value);});
    find('frame').addEventListener('change',e=>setFrame(e.target.value,{scrollIntoView:true}));
    scrub.addEventListener('input',e=>setFrame(e.target.value,{scrollIntoView:true}));
    find('ruler').addEventListener('pointerdown',e=>{
      const rect=canvas.getBoundingClientRect();
      setFrame(pixelGeometry(getDraft()?.snapshot?.context?.maxFrames||1,state.zoom)
        .xToFrame(e.clientX-rect.left),{scrollIntoView:false});
    });
    find('undo').addEventListener('click',()=>restore('undo'));
    find('redo').addEventListener('click',()=>restore('redo'));
    find('duplicate').addEventListener('click',()=>{
      const draft=getDraft();if(!draft?.ok)return;
      commitTracks(duplicateSelection(draft.tracks,state.selection,state.snap,
        draft.snapshot.context.maxFrames,[...state.locks]),'duplicate');
    });
    function deleteSelected(){
      const draft=getDraft();if(!draft?.ok)return;
      commitTracks(deleteSelection(draft.tracks,state.selection,[...state.locks]),'delete');
    }
    find('delete').addEventListener('click',deleteSelected);
    find('space').addEventListener('click',()=>{
      const draft=getDraft();if(!draft?.ok)return;
      const lanes=[...new Set(state.selection.map(s=>s.lane))];
      let current=copy(draft.tracks);
      for(const lane of lanes){
        const result=evenlySpace(current,lane,draft.snapshot.context.maxFrames,[...state.locks]);
        if(!result.ok){onNotice?.(result.message,true);return;}
        current=result.tracks;
      }
      state.selection=[];commitTracks({ok:true,tracks:current},'even-space');
    });
    scroll.addEventListener('keydown',e=>{
      if(e.target instanceof HTMLInputElement||e.target instanceof HTMLTextAreaElement)return;
      if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
        e.preventDefault();setFrame(state.frame+(e.key==='ArrowRight'?state.snap:-state.snap),
          {scrollIntoView:true});
      }
    });
    panel.addEventListener('keydown',e=>{
      const tag=e.target?.tagName;
      if(['INPUT','TEXTAREA','SELECT'].includes(tag))return;
      if((e.key==='Delete'||e.key==='Backspace')&&state.selection.length){
        e.preventDefault();deleteSelected();
      }else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){
        e.preventDefault();restore(e.shiftKey?'redo':'undo');
      }else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){
        e.preventDefault();restore('redo');
      }
    });
    panel.hidden=true;
    return {refresh,setFrame,record(before,key){history.record(before,key);displaySelection();},
      reset(){history.reset();state.selection=[];state.frame=0;state.locks.clear();refresh();},
      locks:state.locks,getSelection:()=>copy(state.selection),undo:()=>restore('undo'),
      redo:()=>restore('redo'),selection:state.selection};
  }
  const api={snapFrame,pixelGeometry,previewShift,duplicateSelection,deleteSelection,
    sceneSegments,evenlySpace,createHistory,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioTimeline=api;
})(typeof window==='object'?window:null);
