/* PS4 local/LAN Ollama storyboard director. Suggestions remain isolated until reviewed. */
(function(root){
  'use strict';
  const copy=x=>JSON.parse(JSON.stringify(x));
  const invalid=(code,message)=>({ok:false,code,message});
  function validateProposal(value,draft,bridge){
    if(!draft?.ok||draft.applied)return invalid('NO_DRAFT','Import or load an editable Studio draft.');
    if(!value||typeof value!=='object'||!value.tracks||!Array.isArray(value.scenes)||
       !value.provenance||value.provenance.provider!=='ollama')
      return invalid('FORMAT','The AI storyboard response is incomplete.');
    if(value.provenance.family!==draft.snapshot.context.model?.family ||
       !['create','refine'].includes(value.provenance.mode))
      return invalid('FAMILY','AI model-family provenance does not match the current project.');
    const checked=bridge.validateTracks(value.tracks,draft.snapshot.context.maxFrames);
    if(!checked.ok)return checked;
    if(!value.scenes.length||value.scenes.length>16||value.scenes.length!==value.provenance.scene_count)
      return invalid('SCENES','The AI returned an invalid scene count.');
    if(value.scenes.some(x=>!Number.isInteger(x.frame)||x.frame<0||
      x.frame>=draft.snapshot.context.maxFrames||
      typeof x.positive!=='string'||x.positive.length>32768))
      return invalid('FRAME','AI scene frames or text were invalid.');
    return {ok:true,tracks:checked.tracks,scenes:copy(value.scenes),
      warnings:Array.isArray(value.warnings)?value.warnings.filter(x=>typeof x==='string').slice(0,40):[],
      provenance:copy(value.provenance)};
  }
  function changes(before,after){
    const items=[];
    for(const lane of ['positive','negative']){
      const old=new Map(before[lane].keyframes.map(x=>[x.frame,x.value]));
      const now=new Map(after[lane].keyframes.map(x=>[x.frame,x.value]));
      for(const frame of [...new Set([...old.keys(),...now.keys()])].sort((a,b)=>a-b)){
        if(old.get(frame)===now.get(frame)&&old.has(frame)===now.has(frame))continue;
        items.push({lane,frame,before:old.has(frame)?old.get(frame):null,
          after:now.has(frame)?now.get(frame):null});
      }
    }
    return items;
  }
  // The outer section starts with [hidden] in Prompt Studio's HTML.
  // Revealing only its inner child leaves the entire AI Director invisible.
  function setVisibility(panel,node,empty,usable){
    panel.hidden=false;
    node.hidden=!usable;
    empty.hidden=usable;
  }
  async function readProgressStream(response,onEvent){
    if(!response.body?.getReader)
      throw Error('Streaming progress is unavailable in this browser. Update your browser to continue.');
    const reader=response.body.getReader();
    const decoder=new TextDecoder();
    let buffer='',result=null;
    function dispatch(line){
      if(!line.trim())return;
      let evt;
      try{evt=JSON.parse(line);}catch(_){throw Error('Ollama progress stream contained invalid JSON.');}
      if(!evt||typeof evt!=='object')throw Error('Invalid Ollama progress event.');
      if(evt.type==='error')throw Error(String(evt.message||'Ollama generation failed.'));
      if(evt.type==='progress'){
        onEvent?.(evt);
      }else if(evt.type==='result'){
        if(result!==null)throw Error('Ollama returned more than one result.');
        result=evt.data;
        onEvent?.(evt);
      }else throw Error('Unexpected Ollama progress event.');
    }
    try{
      while(true){
        const {done,value}=await reader.read();
        if(done)break;
        buffer+=decoder.decode(value,{stream:true});
        if(buffer.length>600000)throw Error('Ollama progress message exceeded the browser safety limit.');
        let newline;
        while((newline=buffer.indexOf('\n'))!==-1){
          const line=buffer.slice(0,newline);
          buffer=buffer.slice(newline+1);
          dispatch(line);
        }
      }
      buffer+=decoder.decode();
      if(buffer.trim())dispatch(buffer);
    }finally{reader.releaseLock();}
    if(result===null)throw Error('Ollama stream ended before a completed storyboard was received.');
    return result;
  }
  function mount({panel,getDraft,onCommit,onNotice,bridge}={}){
    if(!panel)throw Error('AI Story Director container is missing.');
    let working=false,pending=null,controller=null,sequence=0,models=[],connected=false;
    let elapsedTimer=null,startedAt=0,progressState=null;
    const node=document.createElement('section');node.className='ps4-director';
    node.innerHTML=`
      <div class="ps4-head"><div><h3>AI Story Director</h3>
        <p class="muted">Use Ollama on this computer or an explicitly trusted private LAN host.
        Only your story, existing prompt text and project timing/model family are sent.
        No files or images are transmitted.</p></div>
        <span class="ps4-provider">Ollama · text only</span></div>
      <div class="ps4-settings">
        <label>Ollama endpoint <input data-p4="endpoint" type="text"
          value="http://127.0.0.1:11434" maxlength="200" spellcheck="false" autocomplete="off"
          placeholder="http://127.0.0.1:11434"></label>
        <label class="ps4-lan"><input data-p4="lan" type="checkbox">
          Allow my trusted private LAN IP (not public addresses)</label>
        <button type="button" data-p4="connect" class="secondary-button compact">Test Connection / Models</button>
        <label>Installed Ollama model <select data-p4="model">
          <option value="">Test connection to list models</option></select></label>
      </div>
      <div class="ps4-story">
        <label>Story, scene idea or creative direction
          <textarea data-p4="idea" rows="5" maxlength="6000"
            placeholder="Describe the story, recurring characters, setting, emotional arc and visual style…"></textarea></label>
        <div class="ps4-options">
          <label>Mode <select data-p4="mode"><option value="create">Create storyboard</option>
            <option value="refine">Refine existing positive keyframes</option></select></label>
          <label>Number of scenes <input data-p4="scenes" type="number" min="1" max="16" value="4"></label>
          <label class="ps4-negatives"><input data-p4="negative" type="checkbox">
            Also generate negative prompts (replaces negative lane)</label>
        </div>
        <p class="muted ps4-privacy">Suggestions do not apply automatically. Refinement keeps existing positive
        keyframe positions; new storyboards use deterministic frame spacing.
        Existing LoRA tags are preserved verbatim for refinement, with placement
        normalized to the beginning. Reinsert LoRAs intentionally after creating a new storyboard.</p>
        <div class="ps4-actions">
          <button type="button" data-p4="generate" class="primary-button compact">Generate Storyboard</button>
          <button type="button" data-p4="cancel" class="secondary-button compact" disabled>Cancel Request</button>
        </div>
        <div data-p4="activity" class="ps4-activity" hidden aria-label="Ollama generation status">
          <div class="ps4-activity-top">
            <strong data-p4="stage">Preparing request…</strong>
            <output data-p4="elapsed">0s elapsed</output>
          </div>
          <progress aria-label="Generation is running, progress is not a percentage"></progress>
          <p data-p4="detail" class="muted">Ollama has not responded yet.</p>
          <p class="muted ps4-activity-note">Model loading and generation can take time.
            This is live activity feedback, not a predicted completion percentage.
            Cancel stops this browser's streaming request.</p>
        </div>
        <p data-p4="status" class="ps4-status" role="status" aria-live="polite">Import a draft and test the Ollama connection.</p>
      </div>
      <section class="ps4-review" data-p4="review" hidden>
        <h4>AI proposal: review before acceptance</h4>
        <p data-p4="summary" class="muted"></p>
        <div data-p4="warnings"></div>
        <div data-p4="scenes" class="ps4-scene-overview" aria-label="Proposed storyboard scenes"></div>
        <div data-p4="diff"></div>
        <div class="ps4-actions">
          <button type="button" data-p4="accept" class="primary-button compact">
            Accept into Studio Draft</button>
          <button type="button" data-p4="discard" class="secondary-button compact">Discard Proposal</button>
        </div>
      </section>`;
    const empty=document.createElement('div');
    empty.className='ps4-empty';
    empty.innerHTML='<h3>AI Story Director</h3>'+
      '<p class="muted">Open an animation project, then select <strong>Import Existing Prompts</strong> or <strong>Load Draft</strong> to enable Ollama storyboard authoring. No model download or remote service is required for manual editing.</p>';
    panel.append(empty,node);
    const q=name=>node.querySelector('[data-p4="'+name+'"]');
    const draft=()=>getDraft?.();
    // Browser-local, non-secret connection preferences. LAN permission is
    // deliberately not persisted and must be opted into again per session.
    const preference=(key,value)=>{
      try{
        if(value===undefined)return root.localStorage?.getItem('morphorum:ps4:'+key)||'';
        root.localStorage?.setItem('morphorum:ps4:'+key,value);
      }catch(_){return '';}
    };
    const savedEndpoint=preference('endpoint');
    if(savedEndpoint&&savedEndpoint.length<=200)q('endpoint').value=savedEndpoint;
    let preferredModel=preference('model');
    function status(s,bad=false){q('status').textContent=s;q('status').dataset.error=bad?'1':'0';
      if(bad)onNotice?.(s,true);}
    function renderProgress(){
      if(!working||!progressState)return;
      const elapsed=Math.max(0,Math.round((Date.now()-startedAt)/1000));
      q('elapsed').textContent=elapsed+'s elapsed';
      const stages={connecting:'Connecting / loading model',
        responding:'Ollama connected',reasoning:'Model reasoning',
        receiving:'Generating response',
        validating:'Validating storyboard'};
      q('stage').textContent=stages[progressState.stage]||'Waiting for Ollama';
      const chars=Number.isSafeInteger(progressState.characters)?progressState.characters:0;
      const thinking=Number.isSafeInteger(progressState.reasoning_characters)?
        progressState.reasoning_characters:0;
      q('detail').textContent=String(progressState.message||'Waiting for Ollama')+
        (thinking?' · '+thinking.toLocaleString()+' reasoning characters (content hidden)':'')+
        (chars?' · '+chars.toLocaleString()+' output characters received':'')+
        ' · timeout after 240s';
    }
    function startProgress(){
      stopProgress();
      startedAt=Date.now();
      progressState={stage:'connecting',characters:0,
        message:'Request sent to Morphorum; connecting to Ollama…'};
      q('activity').hidden=false;
      renderProgress();
      elapsedTimer=setInterval(renderProgress,1000);
    }
    function stopProgress(){
      if(elapsedTimer!==null){clearInterval(elapsedTimer);elapsedTimer=null;}
      q('activity').hidden=true;
      progressState=null;
    }
    function invalidate(){
      pending=null;q('review').hidden=true;q('accept').disabled=true;
    }
    function context(){
      const d=draft();return Boolean(d?.ok&&!d.applied);
    }
    function refresh(){
      const d=draft(),usable=context();
      setVisibility(panel,node,empty,usable);
      if(!usable){invalidate();return;}
      // Freeze all request inputs while Ollama is evaluating a snapshot.
      for(const field of ['endpoint','lan','model','idea','negative'])
        q(field).disabled=working;
      q('mode').disabled=working;
      q('scenes').disabled=working||q('mode').value==='refine';
      if(q('mode').value==='refine')q('scenes').value=String(d.tracks.positive.keyframes.length);
      q('generate').disabled=working||!models.length||!q('model').value||!q('idea').value.trim()||
        q('idea').value.trim().length<8||(q('mode').value==='refine'&&
        d.tracks.positive.keyframes.length>16);
      q('cancel').disabled=!working;
      q('connect').disabled=working;
      q('accept').disabled=!pending||working;
    }
    function forgetModelList(){
      models=[];connected=false;invalidate();
      const select=q('model');select.replaceChildren();
      const option=document.createElement('option');option.value='';
      option.textContent='Test connection to list models';select.appendChild(option);
      refresh();
    }
    function showProposal(result,base){
      const modifications=changes(base.tracks,result.tracks);
      q('summary').textContent=result.scenes.length+' scenes · '+modifications.length+
        ' changed prompt keyframes · '+result.provenance.family.toUpperCase()+
        ' · '+result.provenance.model+'. No project settings or media will change.';
      q('warnings').replaceChildren();q('diff').replaceChildren();q('scenes').replaceChildren();
      for(const scene of result.scenes){
        const cell=document.createElement('div');cell.className='ps4-scene-card';
        const title=document.createElement('strong');
        title.textContent=(scene.title||'Scene')+' · F'+scene.frame;
        const time=document.createElement('span');time.className='muted';
        time.textContent=Number(scene.time_seconds||0).toFixed(2)+'s';
        cell.append(title,time);q('scenes').appendChild(cell);
      }
      for(const w of result.warnings){
        const p=document.createElement('p');p.className='ps4-warning';p.textContent=w;
        q('warnings').appendChild(p);
      }
      for(const item of modifications.slice(0,64)){
        const details=document.createElement('details');
        const summary=document.createElement('summary');
        summary.textContent=(item.lane==='positive'?'Positive':'Negative')+' · F'+item.frame;
        const before=document.createElement('pre');before.textContent='Before: '+(item.before===null?'(not present)':item.before);
        const after=document.createElement('pre');after.textContent='After: '+(item.after===null?'(not present)':item.after);
        details.append(summary,before,after);q('diff').appendChild(details);
      }
      if(modifications.length>64){
        const notice=document.createElement('p');notice.textContent='Showing the first 64 changed keyframes.';
        q('diff').appendChild(notice);
      }
      q('review').hidden=false;
      q('accept').disabled=!modifications.length;
      status(modifications.length?'Review the proposal below, then accept into the Studio draft.':
        'Ollama returned the same prompts; nothing to apply.');
    }
    async function connect(){
      if(working||!context())return;
      ++sequence;invalidate();working=true;refresh();status('Testing Ollama connection…');
      const id=draft().snapshot.projectId;
      try{
        const response=await fetch('/api/prompt-studio/ollama/models',{method:'POST',cache:'no-store',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({endpoint:q('endpoint').value,allow_lan:q('lan').checked})});
        const data=await response.json();
        if(!response.ok)throw Error(data.detail||'Ollama connection failed.');
        if(draft()?.snapshot.projectId!==id)throw Error('Project changed while connecting.');
        models=Array.isArray(data.models)?data.models:[];
        const select=q('model'),previous=select.value||preferredModel;
        select.replaceChildren();
        for(const model of models){
          const op=document.createElement('option');op.value=model.name;
          op.textContent=model.name+(model.parameter_size?' · '+model.parameter_size:'');
          select.appendChild(op);
        }
        if(models.some(x=>x.name===previous))select.value=previous;
        preferredModel=select.value;
        preference('model',preferredModel);
        connected=true;
        status(models.length+' Ollama model(s) found. Text JSON output support depends on the model.');
      }catch(error){forgetModelList();status(error.message,true);}
      finally{working=false;refresh();}
    }
    function cancel(){
      if(!working)return;
      ++sequence;controller?.abort();controller=null;working=false;
      stopProgress();invalidate();refresh();
      status('Request cancelled; Morphorum will close the Ollama stream when the disconnect is detected.');
    }
    async function generate(){
      const d=draft();
      if(!d?.ok||working||!connected||!q('model').value)return;
      const id=d.snapshot.projectId,rev=d.revision,sourceTracks=copy(d.tracks);
      const mode=q('mode').value;
      const count=mode==='refine'?sourceTracks.positive.keyframes.length:Number(q('scenes').value);
      if(!Number.isInteger(count)||count<1||count>16)return status('Choose between 1 and 16 scenes.',true);
      invalidate();working=true;const seq=++sequence;controller=new AbortController();
      refresh();startProgress();
      status('Ollama generation requested. Progress and elapsed time appear above; draft unchanged.');
      try{
        const response=await fetch('/api/prompt-studio/ollama/generate-stream',{
          method:'POST',cache:'no-store',signal:controller.signal,
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            endpoint:q('endpoint').value,allow_lan:q('lan').checked,model:q('model').value,
            mode,idea:q('idea').value,scene_count:count,
            family:d.snapshot.context.model.family,
            max_frames:d.snapshot.context.maxFrames,fps:d.snapshot.context.fps,
            tracks:sourceTracks,include_negative:q('negative').checked,
          }),
        });
        if(!response.ok){
          const error=await response.json().catch(()=>({}));
          throw Error(error.detail||'AI storyboard generation failed (HTTP '+response.status+').');
        }
        const output=await readProgressStream(response,event=>{
          if(seq!==sequence)return;
          if(event.type==='progress'){
            progressState={stage:event.stage,message:event.message,
              characters:event.characters,reasoning_characters:event.reasoning_characters};
            renderProgress();
          }
        });
        if(seq!==sequence)return;
        if(draft()!==d||d.revision!==rev||draft()?.snapshot?.projectId!==id)
          throw Error('Studio draft changed during generation. Discarding stale AI result.');
        const checked=validateProposal(output,d,bridge);
        if(!checked.ok)throw Error(checked.message);
        pending={result:checked,source:d,revision:rev,projectId:id,
          tracksSignature:JSON.stringify(sourceTracks)};
        showProposal(checked,{tracks:sourceTracks});
      }catch(error){
        if(seq===sequence)status(error.name==='AbortError'?'AI request cancelled.':
          (error.message||'AI request failed.'),error.name!=='AbortError');
      }finally{
        if(seq===sequence){working=false;controller=null;stopProgress();refresh();}
      }
    }
    async function accept(){
      const review=pending,d=draft();
      if(!review||!d?.ok||d!==review.source||d.revision!==review.revision||
         d.snapshot.projectId!==review.projectId||
         JSON.stringify(d.tracks)!==review.tracksSignature){
        invalidate();return status('Draft changed after generation. Generate a fresh proposal.',true);
      }
      if(!root.MorphorumDialog?.confirm)
        return status('Confirmation dialog unavailable; no prompts were changed.',true);
      const yes=await root.MorphorumDialog.confirm({
        title:'Accept AI storyboard into Studio draft?',
        message:'Replace the selected Studio prompt lanes with this reviewed proposal? '+
          'This does not save the project. You can Undo, or discard the Studio draft. '+
          'Existing Prompt Studio Apply/Save remains a separate step.',
        confirmText:'Accept Into Draft',cancelText:'Keep Reviewing'});
      if(!yes)return;
      if(d!==draft()||d.revision!==review.revision){
        invalidate();return status('Draft changed while confirmation was open. Generate again.',true);
      }
      const result=onCommit?.(review.result.tracks,review.result.provenance);
      if(!result?.ok){status(result?.message||'Could not accept the storyboard.',true);return;}
      invalidate();refresh();
      status('AI storyboard staged in the Studio draft. Review the timeline and Save Draft or Apply to Animation when ready.');
    }
    q('connect').addEventListener('click',()=>void connect());
    q('generate').addEventListener('click',()=>void generate());
    q('cancel').addEventListener('click',cancel);
    q('accept').addEventListener('click',()=>void accept());
    q('discard').addEventListener('click',()=>{invalidate();refresh();status('AI proposal discarded. Draft unchanged.');});
    q('idea').addEventListener('input',()=>{invalidate();refresh();});
    q('mode').addEventListener('change',()=>{invalidate();refresh();});
    q('endpoint').addEventListener('change',()=>{
      preference('endpoint',q('endpoint').value.slice(0,200));
      forgetModelList();
    });
    q('lan').addEventListener('change',forgetModelList);
    q('model').addEventListener('change',()=>{
      preferredModel=q('model').value;
      preference('model',preferredModel);
      invalidate();refresh();
    });
    q('negative').addEventListener('change',()=>{invalidate();refresh();});
    q('scenes').addEventListener('change',()=>{invalidate();refresh();});
    refresh();
    return {refresh,invalidate,reset(){cancel();invalidate();forgetModelList();refresh();},
      getPending:()=>pending};
  }
  const api={validateProposal,changes,setVisibility,readProgressStream,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioAI=api;
})(typeof window==='object'?window:null);
