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
      diagnostics:Array.isArray(value.diagnostics)?value.diagnostics.filter(x=>
        x&&['positive','negative'].includes(x.lane)&&Number.isInteger(x.frame)&&
        Number.isInteger(x.words_approx)&&typeof x.long_prompt==='boolean').slice(0,100):[],
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
  // Only server-managed, checksum-addressed project source images can be previewed.
  // Provider-supplied URLs are deliberately ignored.
  function sourceAsset(inventory,projectId){
    if(!inventory||!Array.isArray(inventory.assets)||typeof projectId!=='string')return null;
    const asset=inventory.assets.find(x=>x?.kind==='source_image'&&x.project_id===projectId&&
      x.media_type==='image/png'&&x.id==='source-image'&&
      /^[0-9a-f]{64}$/.test(x.sha256||'')&&Number.isSafeInteger(x.bytes)&&x.bytes>0);
    return asset?{sha256:asset.sha256,bytes:asset.bytes,projectId}:null;
  }
  function appendVisionDescription(idea,description){
    if(typeof idea!=='string'||typeof description!=='string')return null;
    const text=description.trim();
    if(text.length<8||text.length>2400)return null;
    const next=[idea.trim(),'Visual reference from the attached start image (editable description): '+text]
      .filter(Boolean).join('\n\n');
    return next.length<=6000?next:null;
  }
  function mount({panel,getDraft,onCommit,onNotice,bridge}={}){
    if(!panel)throw Error('AI Story Director container is missing.');
    let working=false,pending=null,controller=null,sequence=0,models=[],connected=false;
    let elapsedTimer=null,startedAt=0,progressState=null;
    let profileCatalog=null,profileFetchPending=false,profileFetchAttempted=false,profileFamily='';
    let imageAsset=null,imageAssetKey='',imageBusy=false,visionResult=null,activeVision=false;
    let evalUI=null,evalBusy=false;
    let previewReady=false;
    const node=document.createElement('section');node.className='ps4-director';
    node.innerHTML=`
      <div class="ps4-head"><div><h3>AI Story Director</h3>
        <p class="muted">Use Ollama on this computer or an explicitly trusted private LAN host.
        Normally only your story, existing prompts and project timing/model family are sent.
        Image analysis is separate, optional, and requires explicit per-request consent.</p></div>
        <span class="ps4-provider">Ollama · text / opt-in vision</span></div>
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
        <fieldset class="ps5-profile"><legend>PS5.1 · Model-aware authoring</legend>
          <div class="ps5-settings">
            <label>Prompt profile <select data-p4="profile" aria-label="Model-aware prompt profile">
              <option value="">Checking family profile…</option></select></label>
            <label>Refine selection <select data-p4="target">
              <option value="">All existing positive keyframes</option></select></label>
          </div>
          <p data-p4="profile-note" class="muted">Authoring profile guidance; not renderer capability detection.</p>
          <div class="ps5-settings">
            <label>Lock recurring subject/character description
              <textarea data-p4="subject" rows="2" maxlength="1000"
                placeholder="Exact character identity, clothing, proportions…"></textarea></label>
            <label>Lock visual style / setting
              <textarea data-p4="style" rows="2" maxlength="1000"
                placeholder="Same illustration technique, palette, camera style…"></textarea></label>
          </div>
          <p class="muted">Nonempty locks are repeated literally in accepted generated prompts where missing. They do not change render settings. Refine Selected changes just one positive keyframe; unrelated lanes stay intact.</p>
        </fieldset>
        <fieldset class="ps5-vision">
          <legend>PS5.2 · Analyze attached start image (optional)</legend>
          <p class="muted">This uses only the PNG already attached to this animation project.
            Preview it below. Clicking Analyze transmits a resized copy to the selected
            <strong>loopback Ollama</strong> model on this computer, after its vision capability
            has been verified. Text-model LAN access does not grant image access.
            No image is sent simply by opening this section.</p>
          <div class="ps5-vision-media">
            <img data-p4="vision-preview" alt="Attached project start image preview" hidden>
            <p data-p4="vision-media" class="muted">Checking this project's start image…</p>
          </div>
          <div class="ps4-actions">
            <button type="button" data-p4="vision-refresh" class="secondary-button compact">Refresh Start Image</button>
          </div>
          <label class="ps5-vision-consent">
            <input data-p4="vision-consent" type="checkbox">
            I authorize sending this previewed attached image to the selected local
            Ollama vision model for this request only.
          </label>
          <div class="ps4-actions">
            <button type="button" data-p4="vision-analyze" class="secondary-button compact" disabled>
              Analyze Start Image</button>
          </div>
          <p class="muted" data-p4="vision-status" role="status" aria-live="polite">
            No image analysis requested.</p>
          <div class="ps5-vision-result" data-p4="vision-result" hidden>
            <label>Review and edit the model's visual description
              <textarea data-p4="vision-description" rows="4" maxlength="2400"
                placeholder="Image description appears here after opt-in analysis."></textarea>
            </label>
            <button type="button" data-p4="vision-use" class="secondary-button compact">
              Add Description to Story</button>
            <p class="muted">Adding this text only edits the story input. It does not start
              storyboard generation, modify existing prompts, or save the project.</p>
          </div>
        </fieldset>
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
        <div data-p4="diagnostics" class="ps5-diagnostics" aria-label="Prompt length diagnostics"></div>
        <div data-p4="scenes" class="ps4-scene-overview" aria-label="Proposed storyboard scenes"></div>
        <div data-p4="diff"></div>
        <div class="ps4-actions">
          <button type="button" data-p4="accept" class="primary-button compact">
            Accept into Studio Draft</button>
          <button type="button" data-p4="discard" class="secondary-button compact">Discard Proposal</button>
        </div>
      </section>
      <section data-p4="evaluation" aria-label="PS5.3 local model evaluation"></section>`;
    const empty=document.createElement('div');
    empty.className='ps4-empty';
    empty.innerHTML='<h3>AI Story Director</h3>'+
      '<p class="muted">Open an animation project, then select <strong>Import Existing Prompts</strong> or <strong>Load Draft</strong> to enable Ollama storyboard authoring. No model download or remote service is required for manual editing.</p>';
    panel.append(empty,node);
    // Keep the primary storyboard form visible and tuck secondary tools away.
    function fold(section,label,expanded){
      if(!section)return;
      const details=document.createElement('details');
      details.className='ps5-fold';details.open=expanded;
      const heading=document.createElement('summary');heading.textContent=label;
      section.before(details);details.append(heading,section);
    }
    fold(node.querySelector('.ps5-profile'),'Model-aware authoring · PS5.1',false);
    fold(node.querySelector('.ps5-vision'),'Start-image vision · PS5.2',false);
    fold(node.querySelector('[data-p4="evaluation"]'),'Compare Ollama models · PS5.3',false);
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
        receiving:'Generating response',vision:'Verifying and describing start image',
        validating:'Validating storyboard'};
      q('stage').textContent=stages[progressState.stage]||'Waiting for Ollama';
      const chars=Number.isSafeInteger(progressState.characters)?progressState.characters:0;
      const thinking=Number.isSafeInteger(progressState.reasoning_characters)?
        progressState.reasoning_characters:0;
      q('detail').textContent=String(progressState.message||'Waiting for Ollama')+
        (thinking?' · '+thinking.toLocaleString()+' reasoning characters (content hidden)':'')+
        (chars?' · '+chars.toLocaleString()+' output characters received':'')+
        ' · timeout after '+(activeVision?'150s':'240s');
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
    function clearVisionResult(){
      visionResult=null;q('vision-result').hidden=true;
      q('vision-description').value='';
    }
    function visionStatus(message,bad=false){
      q('vision-status').textContent=message;
      q('vision-status').dataset.error=bad?'1':'0';
    }
    async function fetchSourceAsset(id){
      const response=await fetch('/api/animation/projects/'+encodeURIComponent(id)+
        '/media-inventory',{cache:'no-store'});
      if(!response.ok)throw Error('Project media inventory HTTP '+response.status);
      return sourceAsset(await response.json(),id);
    }
    async function inspectVisionAsset(force=false){
      const d=draft(),id=d?.snapshot?.projectId||'';
      if(!id||!d?.ok)return;
      const key=id+':'+(d.snapshot.context?.sourceImageName||'');
      if(!force&&(imageBusy||imageAssetKey===key))return;
      const old=imageAsset;
      imageAssetKey=key;imageBusy=true;imageAsset=null;previewReady=false;
      q('vision-preview').hidden=true;q('vision-consent').checked=false;
      q('vision-media').textContent='Checking attached start image…';
      clearVisionResult();
      refresh();
      try{
        const asset=await fetchSourceAsset(id);
        if(draft()!==d||imageAssetKey!==key)return;
        imageAsset=asset;
        if(asset){
          const photo=q('vision-preview');
          photo.src='/api/animation/projects/'+encodeURIComponent(id)+
            '/source-image?v='+asset.sha256;
          photo.hidden=false;
          q('vision-media').textContent='Attached project image · '+
            (d.snapshot.context?.sourceImageName||'source.png')+
            ' · '+Math.round(asset.bytes/1024)+' KiB';
          visionStatus(old&&old.sha256!==asset.sha256?
            'Image changed. Review the new preview and explicitly consent again.':
            'Review the image, select an installed vision model, then opt in.');
        }else{
          q('vision-media').textContent='No attached start image found. Attach one in Project Editor first.';
          visionStatus('Image analysis unavailable without an attached project image.');
        }
      }catch(error){
        if(draft()===d){q('vision-media').textContent='Could not inspect attached image.';
          visionStatus(error.message||'Media inventory unavailable.',true);}
      }finally{
        if(draft()===d&&imageAssetKey===key){imageBusy=false;refresh();}
      }
    }
    function isLoopbackEndpoint(){
      try{
        const host=new URL(q('endpoint').value).hostname;
        return host==='localhost'||host==='127.0.0.1'||host==='[::1]'||host==='::1';
      }catch(_){return false;}
    }
    async function analyzeImage(){
      const d=draft(),asset=imageAsset;
      if(!d?.ok||working||evalBusy||imageBusy||!previewReady||!connected||!asset||!q('vision-consent').checked||
         !isLoopbackEndpoint()||!q('model').value)return;
      const id=d.snapshot.projectId,rev=d.revision,sha=asset.sha256;
      q('vision-consent').checked=false;
      clearVisionResult();
      working=true;activeVision=true;const seq=++sequence;controller=new AbortController();
      refresh();startProgress();
      progressState={stage:'vision',characters:0,
        message:'Verifying vision capability before any image is transmitted…'};
      renderProgress();
      visionStatus('Analyzing the previewed image locally; Studio draft unchanged.');
      try{
        const response=await fetch('/api/prompt-studio/ollama/analyze-start-image',{
          method:'POST',cache:'no-store',signal:controller.signal,
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({project_id:id,source_sha256:sha,consent:true,
            endpoint:q('endpoint').value,model:q('model').value}),
        });
        const data=await response.json().catch(()=>({}));
        if(!response.ok)throw Error(data.detail||'Image analysis failed (HTTP '+response.status+').');
        const current=draft();
        if(seq!==sequence)return;
        if(current!==d||d.revision!==rev||current?.snapshot?.projectId!==id)
          throw Error('Studio project or draft changed; discarding stale image description.');
        // Confirm the project media was not replaced while Ollama was processing.
        const latest=await fetchSourceAsset(id);
        if(seq!==sequence)return;
        if(!latest||latest.sha256!==sha||data.source_sha256!==sha||
           data.project_id!==id||data.model!==q('model').value)
          throw Error('Attached start image changed. Refresh the preview before retrying.');
        if(typeof data.description!=='string'||data.description.trim().length<8||
           data.description.length>2400)throw Error('Invalid model description.');
        visionResult={projectId:id,sha256:sha};
        q('vision-description').value=data.description;
        q('vision-result').hidden=false;
        visionStatus('Image description ready for review. Nothing was applied or saved.');
      }catch(error){
        if(seq===sequence)visionStatus(error.name==='AbortError'?'Image analysis cancelled.':
          (error.message||'Image analysis failed.'),error.name!=='AbortError');
      }finally{
        if(seq===sequence){working=false;activeVision=false;controller=null;
          stopProgress();refresh();}
      }
    }
    function useImageDescription(){
      const d=draft();
      if(!visionResult||!d?.ok||d.snapshot.projectId!==visionResult.projectId||
         imageAsset?.sha256!==visionResult.sha256||working)
        return visionStatus('Refresh the image and repeat analysis before using this description.',true);
      const next=appendVisionDescription(q('idea').value,q('vision-description').value);
      if(next===null)return visionStatus('Description is invalid or the story would exceed 6000 characters.',true);
      q('idea').value=next;
      invalidate();refresh();
      visionStatus('Description added to the editable story. Generate Storyboard separately.');
    }
    function context(){
      const d=draft();return Boolean(d?.ok&&!d.applied);
    }
    const profileId=family=>'ps5-'+family+'-v1';
    async function ensureProfiles(){
      if(profileCatalog||profileFetchPending||profileFetchAttempted)return;
      profileFetchPending=true;profileFetchAttempted=true;
      try{
        const response=await fetch('/api/prompt-studio/profiles',{cache:'no-store'});
        if(!response.ok)throw Error('Profile catalog HTTP '+response.status);
        const result=await response.json();
        if(!Array.isArray(result.profiles))throw Error('Invalid authoring profile catalog');
        profileCatalog=result;
      }catch(error){
        q('profile-note').textContent='Profile metadata unavailable: '+error.message+
          '. This does not affect manual prompt editing.';
      }finally{profileFetchPending=false;refresh();}
    }
    function refreshProfile(d){
      const family=d.snapshot.context.model?.family||'';
      const selector=q('profile');
      if(profileFamily!==family||(profileCatalog&&selector.dataset.loadedProfile!==family)){
        profileFamily=family;
        selector.replaceChildren();
        const record=profileCatalog?.profiles?.find(p=>p.family===family);
        selector.dataset.loadedProfile=record?family:'';
        if(record){
          const option=document.createElement('option');option.value=record.id;
          option.textContent=record.name+' · v1';selector.appendChild(option);
          q('profile-note').textContent=record.negative_note+
            ' Length guideline: approximately '+record.guideline_words+
            ' words (not CLIP tokens, and not a hard limit).';
        }else{
          const option=document.createElement('option');option.value=profileId(family);
          option.textContent=family.toUpperCase()+' profile · v1';selector.appendChild(option);
        }
      }
      const target=q('target'),before=target.value;
      target.replaceChildren();
      const all=document.createElement('option');all.value='';all.textContent='All existing positive keyframes';
      target.appendChild(all);
      for(const point of d.tracks.positive.keyframes){
        const item=document.createElement('option');item.value=String(point.frame);
        item.textContent='Only frame '+point.frame;target.appendChild(item);
      }
      if([...target.options].some(x=>x.value===before))target.value=before;
      target.disabled=working||evalBusy||q('mode').value!=='refine';
    }
    function refresh(){
      const d=draft(),usable=context();
      setVisibility(panel,node,empty,usable);
      if(!usable){invalidate();evalUI?.reset();return;}
      if(!profileCatalog&&!profileFetchPending&&!profileFetchAttempted)void ensureProfiles();
      refreshProfile(d);
      // Do not start competing Ollama requests during serial model evaluations.
      const occupied=working||evalBusy;
      for(const field of ['endpoint','lan','model','idea','negative','profile','subject','style'])
        q(field).disabled=occupied;
      q('mode').disabled=occupied;
      q('scenes').disabled=occupied||q('mode').value==='refine';
      if(q('mode').value==='refine')
        q('scenes').value=q('target').value!==''?'1':String(d.tracks.positive.keyframes.length);
      q('generate').disabled=occupied||!models.length||!q('model').value||!q('idea').value.trim()||
        q('idea').value.trim().length<8||(q('mode').value==='refine'&&
        d.tracks.positive.keyframes.length>16);
      q('cancel').disabled=!working;
      q('connect').disabled=occupied;
      q('accept').disabled=!pending||occupied;
      q('vision-refresh').disabled=occupied||imageBusy;
      q('vision-consent').disabled=occupied||imageBusy||!imageAsset;
      q('vision-analyze').disabled=occupied||imageBusy||!previewReady||!imageAsset||!connected||
        !q('model').value||!q('vision-consent').checked||!isLoopbackEndpoint();
      q('vision-description').disabled=occupied;
      q('vision-use').disabled=occupied||!visionResult;
      // Project-owned attached images may be added after the Studio draft import.
      if(!imageBusy&&imageAssetKey!==d.snapshot.projectId+':'+
         (d.snapshot.context?.sourceImageName||''))void inspectVisionAsset();
      evalUI?.refresh();
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
      q('diagnostics').replaceChildren();
      if(Array.isArray(result.diagnostics)){
        const heading=document.createElement('p');
        heading.textContent='Prompt lengths (approximate words, not model tokens):';
        q('diagnostics').appendChild(heading);
        const problematic=result.diagnostics.filter(x=>x.long_prompt);
        const summary=document.createElement('p');summary.textContent=problematic.length?
          problematic.map(x=>x.lane+' F'+x.frame+': '+x.words_approx+' words').join(' · '):
          'No length warnings under the profile heuristics.';
        q('diagnostics').appendChild(summary);
      }
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
      if(working||evalBusy||!context())return;
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
      activeVision=false;visionStatus('Request cancelled; no prompts changed.');
      status('Request cancelled; no Studio or Project Editor changes were made.');
    }
    async function generate(){
      const d=draft();
      if(!d?.ok||working||evalBusy||!connected||!q('model').value)return;
      const id=d.snapshot.projectId,rev=d.revision,sourceTracks=copy(d.tracks);
      const mode=q('mode').value;
      const target=q('target').value;
      const count=mode==='refine'?
        (target!==''?1:sourceTracks.positive.keyframes.length):Number(q('scenes').value);
      if(!Number.isInteger(count)||count<1||count>16)return status('Choose between 1 and 16 scenes.',true);
      invalidate();working=true;activeVision=false;const seq=++sequence;controller=new AbortController();
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
            profile:q('profile').value||profileId(d.snapshot.context.model.family),
            target_frame:mode==='refine'&&target!==''?Number(target):null,
            continuity:{subject:q('subject').value,style:q('style').value},
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
    q('vision-preview').addEventListener('load',()=>{
      previewReady=Boolean(imageAsset&&
        q('vision-preview').currentSrc.includes('v='+imageAsset.sha256));
      if(previewReady)visionStatus('Preview loaded. You may consent to a single analysis request.');
      refresh();
    });
    q('vision-preview').addEventListener('error',()=>{
      previewReady=false;q('vision-consent').checked=false;
      visionStatus('Start image preview could not load. Refresh or repair the attachment.',true);
      refresh();
    });
    q('vision-refresh').addEventListener('click',()=>void inspectVisionAsset(true));
    q('vision-consent').addEventListener('change',refresh);
    q('vision-analyze').addEventListener('click',()=>void analyzeImage());
    q('vision-use').addEventListener('click',useImageDescription);
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
    for(const key of ['profile','target']){
      q(key).addEventListener('change',()=>{invalidate();refresh();});
    }
    for(const key of ['subject','style']){
      q(key).addEventListener('input',()=>{invalidate();refresh();});
    }
    evalUI=root.MorphorumPromptStudioEvaluation?.mount({
      container:q('evaluation'),readStream:readProgressStream,
      getContext:()=>({draft:draft(),models,connected,
        endpoint:q('endpoint').value,allowLan:q('lan').checked,parentBusy:working}),
      onBusy:value=>{evalBusy=value;refresh();}
    })||null;
    if(!evalUI)q('evaluation').textContent='PS5.3 comparison module unavailable. Refresh after updating.';
    refresh();
    return {refresh,invalidate,reset(){evalUI?.reset();
        cancel();invalidate();forgetModelList();
        imageAsset=null;imageAssetKey='';imageBusy=false;previewReady=false;
        q('vision-consent').checked=false;clearVisionResult();
        q('vision-preview').hidden=true;refresh();
      },
      getPending:()=>pending};
  }
  const api={validateProposal,changes,setVisibility,readProgressStream,sourceAsset,
    appendVisionDescription,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioAI=api;
})(typeof window==='object'?window:null);
