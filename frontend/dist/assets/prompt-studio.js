/* PS1.3: manual Prompt Studio workspace. No saves, renders, AI or audio writes. */
(function(root) {
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  const psComposer=root?.MorphorumPromptStudioComposer||
    (typeof module==='object'&&module.exports?require('./prompt-studio-composer.js'):null);
  const psAI=root?.MorphorumPromptStudioAI||
    (typeof module==='object'&&module.exports?require('./prompt-studio-ai.js'):null);
  const problem=(code,message)=>({ok:false,code,message});
  function beginDraft(snapshot,bridge) {
    if(!snapshot?.ok || !snapshot.projectId || !bridge)
      return problem('NO_SNAPSHOT','Import a current Project Editor snapshot first.');
    const maxFrames=Number(snapshot.context?.maxFrames);
    const validation=bridge.validateTracks(snapshot.promptTracks,maxFrames);
    if(!validation.ok) return validation;
    return {ok:true,snapshot:clone(snapshot),original:clone(validation.tracks),
      tracks:clone(validation.tracks),composer:psComposer?.blank()||{schema_version:1,blocks:[]},
      aiProvenance:null,revision:0,applied:false};
  }
  function updateDraft(draft,bridge,lane,operation,frame,value) {
    if(!draft?.ok||draft.applied) return problem('NO_DRAFT','Import editable prompts first.');
    if(!['positive','negative'].includes(lane)) return problem('LANE','Unknown prompt lane.');
    const n=Number(frame),limit=Number(draft.snapshot.context.maxFrames);
    if(operation!=='interpolation' && (!Number.isInteger(n)||n<0||n>=limit))
      return problem('FRAME','Use a whole frame number between 0 and '+(limit-1)+'.');
    const next=clone(draft.tracks);
    const target=next[lane],points=target.keyframes;
    const at=points.findIndex(p=>p.frame===n);
    if(operation==='interpolation') {
      if(value!=='blend'&&value!=='hold') return problem('MODE','Choose Hold or Blend.');
      target.interpolation=value;
    } else if(operation==='add') {
      if(at!==-1) return problem('COLLISION','This lane already has a keyframe at F'+n+'.');
      points.push({frame:n,value:''});
      points.sort((a,b)=>a.frame-b.frame);
    } else if(operation==='remove') {
      if(n===0) return problem('FRAME_ZERO','Frame 0 is required in both lanes.');
      if(at===-1) return problem('NOT_FOUND','This lane has no keyframe at F'+n+'.');
      points.splice(at,1);
    } else if(operation==='text') {
      if(at===-1) return problem('NOT_FOUND','Keyframe was not found.');
      if(typeof value!=='string') return problem('TEXT','Prompt text must be a string.');
      points[at].value=value;
    } else if(operation==='move') {
      const to=Number(value);
      if(!Number.isInteger(to)||to<0||to>=limit)
        return problem('FRAME','Destination must be between 0 and '+(limit-1)+'.');
      if(n===0) return problem('FRAME_ZERO','Frame 0 cannot be moved.');
      if(at===-1) return problem('NOT_FOUND','Keyframe was not found.');
      if(points.some(p=>p.frame===to))
        return problem('COLLISION','A keyframe already exists at F'+to+'.');
      points[at].frame=to;
      points.sort((a,b)=>a.frame-b.frame);
    } else return problem('OPERATION','Unsupported keyframe operation.');
    const checked=bridge.validateTracks(next,limit);
    if(!checked.ok) return checked;
    draft.tracks=checked.tracks;
    draft.revision+=1;
    return {ok:true,revision:draft.revision};
  }
  function changeList(original,proposed) {
    const changes=[];
    for(const lane of ['positive','negative']) {
      const a=original[lane],b=proposed[lane];
      if(a.interpolation!==b.interpolation)
        changes.push({lane,frame:null,kind:'Interpolation',before:a.interpolation,after:b.interpolation});
      const old=new Map(a.keyframes.map(p=>[p.frame,p.value]));
      const now=new Map(b.keyframes.map(p=>[p.frame,p.value]));
      for(const frame of [...new Set([...old.keys(),...now.keys()])].sort((x,y)=>x-y)){
        if(old.has(frame)&&now.has(frame)&&old.get(frame)===now.get(frame))continue;
        changes.push({lane,frame,kind:!old.has(frame)?'Added':!now.has(frame)?'Removed':'Changed',
          before:old.has(frame)?old.get(frame):null,after:now.has(frame)?now.get(frame):null});
      }
    }
    return changes;
  }

  // PS1.4 draft format is independent of ephemeral Editor revision/ETag.
  function serializeDraft(draft,name,bridge) {
    if(!draft?.ok) return problem('NO_DRAFT','Import or load a draft before saving.');
    const title=String(name||'').trim();
    if(!title || title.length>120) return problem('INVALID_NAME','Enter a draft name (1–120 characters).');
    const frames=Number(draft.snapshot?.context?.maxFrames);
    const original=bridge.validateTracks(draft.original,frames);
    const edited=bridge.validateTracks(draft.tracks,frames);
    if(!original.ok)return original;
    if(!edited.ok)return edited;
    const context=draft.snapshot.context;
    const composed=psComposer?.normalize(draft.composer,frames);
    if(!composed?.ok)return composed||problem('COMPOSER','Composer validation unavailable.');
    return {ok:true,record:{
      format:'morphorum.prompt-studio-draft',schema_version:1,
      project_id:draft.snapshot.projectId,name:title,
      project_context:{model:clone(context.model),max_frames:frames,fps:Number(context.fps),
        start_mode:context.startMode||'prompt',source_image_name:context.sourceImageName||''},
      original_tracks:original.tracks,prompt_tracks:edited.tracks,composer:composed.composer,
      ai_provenance:draft.aiProvenance||null
    }};
  }
  function restoreDraft(saved,live,bridge) {
    if(!saved||saved.format!=='morphorum.prompt-studio-draft'||saved.schema_version!==1)
      return problem('INVALID_DRAFT','Unrecognized saved Studio draft.');
    if(!saved.project_id||!saved.project_context)
      return problem('INVALID_DRAFT','Saved project reference is missing.');
    const original=bridge.validateTracks(saved.original_tracks,saved.project_context.max_frames);
    const edited=bridge.validateTracks(saved.prompt_tracks,saved.project_context.max_frames);
    if(!original.ok)return original;
    if(!edited.ok)return edited;
    const model=(record)=>JSON.stringify([
      record?.model?.model_id||'',record?.model?.family||'',record?.model?.variant||'']);
    const expected=saved.project_context,actual=live?.context;
    const compatible=Boolean(live?.ok&&live.projectId===saved.project_id &&
      Number(expected.max_frames)===Number(actual.maxFrames) &&
      Number(expected.fps)===Number(actual.fps) &&
      model(expected)===model(actual) &&
      (expected.start_mode||'prompt')===(actual.startMode||'prompt') &&
      (expected.source_image_name||'')===(actual.sourceImageName||'') &&
      JSON.stringify(original.tracks)===JSON.stringify(live.promptTracks));
    const snapshot=compatible?clone(live):{
      ok:false,projectId:saved.project_id,
      context:{name:saved.name,model:clone(expected.model),maxFrames:expected.max_frames,
        fps:expected.fps,startMode:expected.start_mode,sourceImageName:expected.source_image_name}
    };
    const composed=psComposer?.normalize(saved.composer,saved.project_context.max_frames);
    if(!composed?.ok)return composed||problem('COMPOSER','Composer validation unavailable.');
    return {ok:true,original:original.tracks,tracks:edited.tracks,
      composer:composed.composer,aiProvenance:saved.ai_provenance||null,
      snapshot,revision:0,applied:false,compatible};
  }
  function mount({panel,onEditor}={}) {
    if(!panel) throw new Error('Prompt Studio panel is required.');
    const bridge=root.MorphorumPromptStudioBridge;
    let draft=null,busy=false,invalid=false,previewedRevision=-1,blocked=false;
    let baselineBlocked=false,savedId='',savedEtag='',savedRevision=-1;
    let shownProjectId='',libraryEntries=[];
    let timeline=null,composerUI=null,aiUI=null;
    const dom=document.createElement('article');
    dom.className='card glass ps13-workspace';
    dom.innerHTML=`
      <div class="ps13-head">
        <div><p class="eyebrow">PROJECTS / PROMPT STUDIO</p>
          <h2>Prompt Studio</h2>
          <p class="muted">Import a live Project Editor draft. Edit positive and negative prompts independently, then preview and apply them back to the Editor.</p></div>
        <button class="secondary-button compact" type="button" data-ps="editor">← Project Editor</button>
      </div>
      <div class="ps13-actions">
        <button class="primary-button compact" type="button" data-ps="import">Import Existing Prompts</button>
        <button class="secondary-button compact" type="button" data-ps="reset" disabled>Reset Draft</button>
        <button class="secondary-button compact" type="button" data-ps="preview" disabled>Preview Changes</button>
        <button class="primary-button compact" type="button" data-ps="apply" disabled>Apply to Animation</button>
      </div>
      <section class="ps14-library" aria-label="Saved Prompt Studio drafts">
        <div class="ps14-library-heading"><strong>Saved drafts</strong>
          <span class="muted">Stored in this project; included in its verified ZIP / Save As copy</span></div>
        <div class="ps14-library-controls">
          <label>Saved draft <select data-ps="saved" aria-label="Saved Prompt Studio draft">
            <option value="">No drafts loaded</option></select></label>
          <button class="secondary-button compact" type="button" data-ps="load">Load Draft</button>
          <button class="secondary-button compact" type="button" data-ps="refresh">Refresh List</button>
          <button class="secondary-button compact" type="button" data-ps="delete">Delete Draft</button>
        </div>
        <div class="ps14-library-controls">
          <label>Draft name <input data-ps="name" type="text" maxlength="120" placeholder="Storyboard draft"></label>
          <button class="primary-button compact" type="button" data-ps="save">Save Draft</button>
          <button class="secondary-button compact" type="button" data-ps="save-copy">Save As New Draft</button>
        </div>
        <p class="muted ps14-library-note" data-ps="library-note" role="status" aria-live="polite">Open an animation project to browse its saved drafts.</p>
      </section>
      <div class="ps13-context" data-ps="context">No prompts imported. Open a project in Project Editor, then select Import Existing Prompts.</div>
      <p class="ps13-notice muted">Import and timeline edits stay in the Studio draft. Preview Changes and confirm Apply before saving in Project Editor. Visual keyframe changes have in-session Undo/Redo; Save Draft persists tracks, not the undo history. Ollama storyboard suggestions require explicit review; audio storyboard synchronization remains planned for PS6.</p>
      <p class="ps13-status" data-ps="status" role="status" aria-live="polite">Ready to import.</p>
      <section class="ps4-workspace" data-ps="ai" hidden aria-label="Ollama AI Story Director"></section>
      <section class="ps3-workspace" data-ps="composer" hidden aria-label="Structured Prompt Composer"></section>
      <section class="ps2-workspace" data-ps="timeline" hidden aria-label="Visual Prompt Studio timeline"></section>
      <div class="ps13-lanes" data-ps="lanes" hidden></div>
      <section class="ps13-review" data-ps="review" aria-label="Prompt transfer preview" hidden>
        <h3>Changes to Project Editor</h3>
        <p class="muted" data-ps="summary"></p>
        <div data-ps="changes"></div>
      </section>`;
    panel.appendChild(dom);
    const find=k=>dom.querySelector('[data-ps="'+k+'"]');
    const importButton=find('import'),resetButton=find('reset'),
      previewButton=find('preview'),applyButton=find('apply'),
      lanes=find('lanes'),review=find('review'),context=find('context');
    const savedSelect=find('saved'),nameInput=find('name'),note=find('library-note');
    const timelinePanel=find('timeline'),composerPanel=find('composer'),
      aiPanel=find('ai');
    const saveButton=find('save'),saveCopyButton=find('save-copy'),
      loadButton=find('load'),deleteButton=find('delete'),refreshButton=find('refresh');
    const projectId=()=>root.MorphorumAnimation?.getPromptStudioProjectId?.()||'';
    const endpoint=(id=projectId())=>'/api/animation/projects/'+
      encodeURIComponent(id)+'/prompt-studio/drafts';
    const libraryStatus=(message)=>{note.textContent=message;};
    async function request(url,options={}) {
      const response=await fetch(url,{cache:'no-store',
        ...options,headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),
          ...(options.headers||{})}});
      let json;
      try {json=await response.json();}catch(_){throw new Error('Invalid draft service response.');}
      if(!response.ok)throw new Error(response.status===412
        ? 'Draft changed in another browser. Refresh and reload before overwriting.'
        : (json?.detail||response.status+' '+response.statusText));
      return {data:json,etag:response.headers.get('ETag')||''};
    }

    const status=(message,error=false)=>{
      const el=find('status');el.textContent=message;
      el.dataset.level=error?'error':'info';
    };
    const previewClear=()=>{previewedRevision=-1;review.hidden=true;applyButton.disabled=true;};
    const count=()=>draft?changeList(draft.original,draft.tracks).length:0;
    function controls(){
      const can=Boolean(draft?.ok&&!draft.applied&&!busy);
      importButton.disabled=busy;
      resetButton.disabled=!can;
      previewButton.disabled=!can||invalid||count()===0;
      applyButton.disabled=!can||invalid||blocked||baselineBlocked||
        previewedRevision!==draft?.revision||count()===0;
      saveButton.disabled=busy||!draft?.ok||projectId()!==draft.snapshot.projectId;
      saveCopyButton.disabled=saveButton.disabled;
      loadButton.disabled=busy||!savedSelect.value||!projectId();
      deleteButton.disabled=loadButton.disabled;
      refreshButton.disabled=busy||!projectId();
      savedSelect.disabled=busy||!projectId();
      nameInput.disabled=busy||!draft?.ok;
      composerUI?.refresh();
      aiUI?.refresh();
      lanes.querySelectorAll('button,input,textarea,select').forEach(el=>{
        el.disabled=!can||el.dataset.psFixed==='1';
      });
    }
    function makeEdit(lane,operation,frame,value,redraw=false){
      if(timeline?.locks?.has(lane))
        return onEdit(problem('LOCKED','Unlock the '+lane+' lane before editing.'));
      const before=draft?.ok?clone(draft.tracks):null;
      const result=updateDraft(draft,bridge,lane,operation,frame,value);
      if(result.ok&&before&&JSON.stringify(before)!==JSON.stringify(draft.tracks))
        timeline?.record(before,operation==='text'?'text:'+lane+':'+frame:operation);
      onEdit(result,redraw);
      return result;
    }
    function applyTracks(next,key,old,historyReplay=false){
      if(!draft?.ok||draft.applied)
        return problem('NO_DRAFT','Load a Studio draft before editing its timeline.');
      const valid=bridge.validateTracks(next,draft.snapshot.context.maxFrames);
      if(!valid.ok)return valid;
      const before=old||clone(draft.tracks);
      if(!historyReplay&&JSON.stringify(before)!==JSON.stringify(valid.tracks))
        timeline?.record(before,key);
      draft.tracks=valid.tracks;draft.revision+=1;
      onEdit({ok:true,revision:draft.revision},true);
      return {ok:true};
    }
    function onEdit(result,redraw=false){
      if(!result.ok){invalid=true;status(result.message,true);controls();return;}
      invalid=false;blocked=false;previewClear();
      status(baselineBlocked
        ? 'Edited saved draft. Its original Project Editor baseline has changed; Apply remains blocked. Save the draft, or manually reimport current prompts.'
        : count()+' staged change(s). Preview Changes before applying.');
      if(redraw)renderLanes();
      else controls();
      timeline?.refresh();
      composerUI?.invalidate();composerUI?.refresh();
      aiUI?.invalidate();aiUI?.refresh();
    }
    function makeLane(name){
      const track=draft.tracks[name];
      const section=document.createElement('section');
      section.className='ps13-lane';
      const heading=document.createElement('div');heading.className='ps13-lane-heading';
      const title=document.createElement('h3');title.textContent=name==='positive'?'Positive prompts':'Negative prompts';
      const modeLabel=document.createElement('label');modeLabel.textContent='Transition ';
      const mode=document.createElement('select');
      mode.dataset.psFixed=timeline?.locks.has(name)?'1':'0';
      mode.setAttribute('aria-label',name+' prompt transition');
      for(const option of ['blend','hold']){
        const opt=document.createElement('option');opt.value=option;
        opt.textContent=option==='blend'?'Blend':'Hold';mode.appendChild(opt);
      }
      mode.value=track.interpolation;
      mode.addEventListener('change',()=>makeEdit(name,'interpolation',0,mode.value));
      modeLabel.appendChild(mode);heading.append(title,modeLabel);
      section.appendChild(heading);
      const rows=document.createElement('div');rows.className='ps13-rows';
      for(const point of track.keyframes){
        const row=document.createElement('div');row.className='ps13-row';
        const frameLabel=document.createElement('label');frameLabel.textContent='Frame';
        const frame=document.createElement('input');frame.type='number';
        frame.min='0';frame.max=String(draft.snapshot.context.maxFrames-1);
        frame.step='1';frame.value=String(point.frame);
        frame.dataset.psFixed=point.frame===0||timeline?.locks.has(name)?'1':'0';
        frame.disabled=point.frame===0;
        frame.setAttribute('aria-label',name+' keyframe '+point.frame+' frame');
        frame.addEventListener('change',()=>{
          const result=makeEdit(name,'move',point.frame,frame.value,true);
          if(!result.ok)frame.value=String(point.frame);
        });frameLabel.appendChild(frame);
        const textLabel=document.createElement('label');textLabel.textContent='Prompt at F'+point.frame;
        const textarea=document.createElement('textarea');textarea.rows=3;textarea.value=point.value;
        textarea.maxLength=32768;textarea.dataset.psFixed=timeline?.locks.has(name)?'1':'0';
        textarea.placeholder=name==='positive'?'Describe this scene…':'Avoid these visual elements…';
        textarea.setAttribute('aria-label',name+' prompt at frame '+point.frame);
        textarea.addEventListener('input',()=>makeEdit(name,'text',point.frame,textarea.value));
        textLabel.appendChild(textarea);
        const remove=document.createElement('button');remove.type='button';
        remove.className='secondary-button compact';remove.textContent='Remove';
        remove.dataset.psFixed=point.frame===0||timeline?.locks.has(name)?'1':'0';
        remove.disabled=point.frame===0;
        remove.addEventListener('click',()=>makeEdit(name,'remove',point.frame,undefined,true));
        row.append(frameLabel,textLabel,remove);rows.appendChild(row);
      }
      section.appendChild(rows);
      const actions=document.createElement('div');actions.className='ps13-add';
      const addLabel=document.createElement('label');addLabel.textContent='New keyframe at frame ';
      const at=document.createElement('input');at.type='number';at.min='0';
      at.max=String(draft.snapshot.context.maxFrames-1);at.step='1';
      at.value=String(Math.min(draft.snapshot.context.maxFrames-1,
        (track.keyframes[track.keyframes.length-1]?.frame||0)+1));
      at.setAttribute('aria-label','New '+name+' keyframe frame');
      addLabel.appendChild(at);
      const add=document.createElement('button');add.className='secondary-button compact';
      add.type='button';add.textContent='+ Add Keyframe';
      add.addEventListener('click',()=>makeEdit(name,'add',at.value,undefined,true));
      at.dataset.psFixed=timeline?.locks.has(name)?'1':'0';
      add.dataset.psFixed=timeline?.locks.has(name)?'1':'0';
      actions.append(addLabel,add);section.appendChild(actions);
      return section;
    }
    function renderLanes(){
      lanes.replaceChildren();if(draft?.ok&&!draft.applied){
        lanes.append(makeLane('positive'),makeLane('negative'));
        lanes.hidden=false;
      } else if(draft?.ok&&draft.applied){
        lanes.hidden=true;
      } else lanes.hidden=true;
      controls();
    }
    function showContext(){
      if(!draft?.ok){context.textContent='No prompts imported. Open a project in Project Editor, then select Import Existing Prompts.';return;}
      const s=draft.snapshot,c=s.context;
      context.replaceChildren();
      const facts=[
        ['Project',c.name||s.projectId],
        ['Checkpoint',String(c.model?.model_id||'Unselected')],
        ['Family',String(c.model?.family||'Unknown')],
        ['Timeline',c.maxFrames+' frames · '+c.fps+' FPS · '+(c.maxFrames/c.fps).toFixed(2)+' sec'],
        ['Start',c.sourceImageName||c.startMode||'Prompt'],
        ['Editor at import',s.dirty?'Unsaved draft':'Saved project']
      ];
      for(const [label,value] of facts){
        const cell=document.createElement('div');
        const strong=document.createElement('strong');strong.textContent=label;
        const span=document.createElement('span');span.textContent=String(value);
        cell.append(strong,span);context.appendChild(cell);
      }
    }
    async function importPrompts(){
      if(busy)return;
      const editor=root.MorphorumAnimation;
      if(!editor?.getPromptStudioEditorSnapshot){status('Project Editor bridge is unavailable.',true);return;}
      if(draft?.ok&&!draft.applied&&count()){
        if(!root.MorphorumDialog?.confirm){status('Confirmation dialog unavailable. Existing draft preserved.',true);return;}
        const proceed=await root.MorphorumDialog.confirm({
          title:'Replace Prompt Studio draft?',
          message:'Reimporting discards the unsaved Prompt Studio changes. It does not modify Project Editor.',
          confirmText:'Replace Draft',cancelText:'Keep Draft'});
        if(!proceed)return;
      }
      busy=true;controls();status('Reading the current Project Editor draft…');
      try {
        const snapshot=await editor.getPromptStudioEditorSnapshot();
        const result=beginDraft(snapshot,bridge);
        if(!result.ok){status(result.message,true);return;}
        draft=result;timeline?.reset();composerUI?.reset();aiUI?.reset();invalid=false;blocked=false;baselineBlocked=false;
        savedId='';savedEtag='';savedRevision=-1;
        nameInput.value=(result.snapshot.context.name||'Storyboard')+' Prompt Draft';
        previewClear();showContext();renderLanes();
        status('Imported '+(draft.tracks.positive.keyframes.length+draft.tracks.negative.keyframes.length)+
          ' original keyframes. Editing here does not change Project Editor.');
      } catch(error){status(error.message||String(error),true);}
      finally{busy=false;controls();}
    }
    function reset(){
      if(!draft?.ok||draft.applied)return;
      draft.tracks=clone(draft.original);
      draft.composer=psComposer?.blank()||{schema_version:1,blocks:[]};
      draft.aiProvenance=null;
      draft.revision+=1;
      timeline?.reset();composerUI?.reset();aiUI?.reset();
      invalid=false;blocked=false;previewClear();renderLanes();
      status('Prompt Studio draft restored to its imported baseline. Project Editor unchanged.');
    }
    function paintChanges(changes){
      const host=find('changes');host.replaceChildren();
      for(const item of changes.slice(0,50)){
        const details=document.createElement('details');details.className='ps13-change';
        const head=document.createElement('summary');
        head.textContent=(item.lane==='positive'?'Positive':'Negative')+' · '+
          (item.frame===null?'transition':'Frame '+item.frame)+' · '+item.kind;
        const body=document.createElement('div');
        for(const [label,value] of [['Before',item.before],['After',item.after]]){
          const block=document.createElement('div'),h=document.createElement('strong'),p=document.createElement('pre');
          h.textContent=label;p.textContent=value===null?'(not present)':value;
          block.append(h,p);body.appendChild(block);
        }
        details.append(head,body);host.appendChild(details);
      }
      if(changes.length>50){const note=document.createElement('p');note.className='muted';
        note.textContent='Showing first 50 of '+changes.length+' changes.';host.appendChild(note);}
    }
    async function preview(){
      if(!draft?.ok||invalid||draft.applied||busy)return;
      if(baselineBlocked){
        status('This draft belongs to an older Editor baseline. Apply is blocked; reimport current prompts before transferring.',true);
        return;
      }
      const editor=root.MorphorumAnimation;
      const result=editor?.previewPromptStudioTransfer?.(draft.snapshot,draft.tracks);
      if(!result?.ok){blocked=true;previewClear();status(result?.message||'Project Editor changed. Reimport its prompts.',true);controls();return;}
      blocked=false;const changes=changeList(draft.original,draft.tracks);
      previewedRevision=draft.revision;
      find('summary').textContent=result.diff.total+' native prompt item(s) to apply. '+
        'The Project Editor project stays unsaved until you select Save Project.';
      paintChanges(changes);review.hidden=false;controls();
      status('Review the changes below, then Apply to Animation.');
    }
    async function apply(){
      if(!draft?.ok||invalid||busy||baselineBlocked||previewedRevision!==draft.revision||blocked)return;
      busy=true;controls();
      status('Confirm the prompt-only transfer to Project Editor…');
      try {
        const result=await root.MorphorumAnimation?.applyPromptStudioTransfer?.(draft.snapshot,draft.tracks);
        if(!result?.ok){blocked=result?.code!=='CANCELLED';status(result?.message||'Apply failed.',true);return;}
        if(result.applied){
          draft.applied=true;timeline?.reset();composerUI?.reset();aiUI?.reset();previewClear();renderLanes();
          status('Prompts staged in Project Editor. Save Project there to persist.');
          onEditor?.();
        }else status(result.message||'No prompt changes to apply.');
      }catch(error){status(error.message||String(error),true);}
      finally{busy=false;controls();}
    }

    async function refreshList({quiet=false}={}) {
      const id=projectId();
      if(!id){
        shownProjectId='';libraryEntries=[];savedSelect.replaceChildren();
        const empty=document.createElement('option');empty.value='';
        empty.textContent='Open a project first';savedSelect.appendChild(empty);
        libraryStatus('Open a project in Project Editor to list drafts.');
        controls();return;
      }
      try {
        const result=await request(endpoint(id));
        if(projectId()!==id)return;
        shownProjectId=id;libraryEntries=result.data.drafts||[];
        const selected=savedSelect.value;
        savedSelect.replaceChildren();
        const empty=document.createElement('option');empty.value='';
        empty.textContent=libraryEntries.length?'Select saved draft…':'No saved drafts yet';
        savedSelect.appendChild(empty);
        for(const item of libraryEntries){
          const option=document.createElement('option');option.value=item.draft_id;
          option.textContent=item.name+' · '+item.updated_at;
          savedSelect.appendChild(option);
        }
        savedSelect.value=libraryEntries.some(e=>e.draft_id===selected)?selected:
          libraryEntries.some(e=>e.draft_id===savedId)?savedId:'';
        libraryStatus(libraryEntries.length+' draft(s) stored with this project.');
      }catch(error){if(!quiet)libraryStatus('Draft list failed: '+error.message);}
      controls();
    }
    async function confirmReplace(){
      if(!draft?.ok||draft.applied||(!count()&&draft.revision===savedRevision))return true;
      if(!root.MorphorumDialog?.confirm)return false;
      return Boolean(await root.MorphorumDialog.confirm({
        title:'Discard current Studio edits?',
        message:'Loading another draft replaces the current browser-memory Studio edits. It does not change Project Editor or delete a saved draft.',
        confirmText:'Load Draft',cancelText:'Keep Editing'}));
    }
    async function loadSaved(){
      const id=projectId(),identifier=savedSelect.value;
      if(busy||!id||!identifier)return;
      if(!(await confirmReplace()))return;
      busy=true;controls();
      try {
        const loaded=await request(endpoint(id)+'/'+encodeURIComponent(identifier));
        let live;
        try {live=await root.MorphorumAnimation?.getPromptStudioEditorSnapshot?.();}
        catch(error){live={ok:false,message:error.message};}
        if(projectId()!==id)throw new Error('Project changed while loading draft.');
        const value=restoreDraft(loaded.data.draft,live,bridge);
        if(!value.ok)throw new Error(value.message);
        draft=value;timeline?.reset();composerUI?.reset();aiUI?.reset();
        invalid=false;blocked=false;baselineBlocked=!value.compatible;
        savedId=identifier;savedEtag=loaded.etag;savedRevision=0;
        nameInput.value=loaded.data.draft.name;
        previewClear();showContext();renderLanes();
        status(value.compatible?'Draft loaded. Its baseline matches Project Editor; preview before applying.'
          :'Draft loaded for editing, but Project Editor has changed since its original import. Apply is disabled to protect current project prompts.',
          !value.compatible);
      }catch(error){status('Could not load draft: '+error.message,true);}
      finally{busy=false;controls();}
    }
    async function saveDraft(asNew=false){
      if(!draft?.ok||busy)return;
      const id=projectId();
      if(!id||draft.snapshot.projectId!==id){
        status('Switch back to this draft’s original animation project before saving.',true);return;
      }
      const serialized=serializeDraft(draft,nameInput.value,bridge);
      if(!serialized.ok){status(serialized.message,true);return;}
      busy=true;controls();
      try{
        const overwrite=!asNew&&Boolean(savedId);
        if(overwrite&&!/^"[a-f0-9]{64}"$/.test(savedEtag))
          throw new Error('Saved draft revision is unknown. Reload it before overwrite.');
        const url=overwrite?endpoint(id)+'/'+encodeURIComponent(savedId):endpoint(id);
        const result=await request(url,{
          method:overwrite?'PUT':'POST',
          headers:overwrite?{'If-Match':savedEtag}:{},
          body:JSON.stringify(serialized.record)
        });
        if(projectId()!==id)throw new Error('Project changed while saving draft. Refresh its library.');
        savedId=result.data.draft.draft_id;savedEtag=result.etag;savedRevision=draft.revision;
        nameInput.value=result.data.draft.name;
        await refreshList({quiet:true});
        libraryStatus('Saved '+result.data.draft.name+' in this project. Camera/render settings were not changed.');
        status('Studio draft saved. Project Editor remains unchanged.');
      }catch(error){status('Draft save failed: '+error.message,true);}
      finally{busy=false;controls();}
    }
    async function deleteSaved(){
      const id=projectId(),identifier=savedSelect.value;
      if(busy||!id||!identifier)return;
      if(!root.MorphorumDialog?.confirm){
        status('Confirmation dialog unavailable; nothing deleted.',true);return;
      }
      const label=libraryEntries.find(entry=>entry.draft_id===identifier)?.name||identifier;
      const confirmed=await root.MorphorumDialog.confirm({
        title:'Delete saved Prompt Studio draft?',
        message:'Delete "'+label+'" from this project? This does not change Project Editor or any saved render.',
        variant:'danger',confirmText:'Delete Draft',cancelText:'Cancel'});
      if(!confirmed||projectId()!==id)return;
      busy=true;controls();
      try{
        // Use the selected list revision, not an unrelated currently loaded draft ETag.
        const item=libraryEntries.find(entry=>entry.draft_id===identifier);
        if(!item)throw new Error('Selected draft was not found; refresh the library.');
        await request(endpoint(id)+'/'+encodeURIComponent(identifier),{
          method:'DELETE',headers:{'If-Match':item.etag}
        });
        if(savedId===identifier){savedId='';savedEtag='';savedRevision=-1;}
        savedSelect.value='';await refreshList({quiet:true});
        libraryStatus('Saved draft deleted. Your current browser editor is not modified.');
      }catch(error){status('Draft delete failed: '+error.message,true);}
      finally{busy=false;controls();}
    }

    aiUI=psAI?.mount({
      panel:aiPanel,getDraft:()=>draft,bridge,
      onCommit:(tracks,provenance)=>{
        const result=applyTracks(tracks,'ollama-storyboard');
        if(result?.ok)draft.aiProvenance=provenance;
        return result;
      },
      onNotice:(message,error)=>{if(error)status(message,true);}
    })||null;
    composerUI=psComposer?.mount({
      panel:composerPanel,getDraft:()=>draft,
      onChange:next=>{
        if(!draft?.ok||draft.applied)return problem('NO_DRAFT','No editable Studio draft.');
        draft.composer=next;draft.revision+=1;previewClear();controls();return {ok:true};
      },
      onCommit:next=>applyTracks(next,'composer'),
      onNotice:(message,error)=>{if(error)status(message,true);}
    })||null;
    timeline=root.MorphorumPromptStudioTimeline?.mount({
      panel:timelinePanel,getDraft:()=>draft,onTracks:applyTracks,
      onNotice:(message,error)=>{status(message,error);renderLanes();},
    })||null;
    find('editor').addEventListener('click',()=>onEditor?.());
    importButton.addEventListener('click',()=>void importPrompts());
    resetButton.addEventListener('click',reset);
    previewButton.addEventListener('click',()=>void preview());
    applyButton.addEventListener('click',()=>void apply());
    saveButton.addEventListener('click',()=>void saveDraft());
    saveCopyButton.addEventListener('click',()=>void saveDraft(true));
    loadButton.addEventListener('click',()=>void loadSaved());
    deleteButton.addEventListener('click',()=>void deleteSaved());
    refreshButton.addEventListener('click',()=>void refreshList());
    savedSelect.addEventListener('change',controls);
    controls();
    return {getState:()=>draft?{projectId:draft.snapshot.projectId,
      applied:draft.applied,changes:count(),revision:draft.revision}:null,
      onShow:()=>{
        if(!draft)status('Import Existing Prompts reads the open Project Editor, including its unsaved prompt text.');
        if(shownProjectId!==projectId())void refreshList();
        else controls();
      }};
  }
  const api={beginDraft,updateDraft,changeList,serializeDraft,restoreDraft,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioWorkspace=api;
})(typeof window==='object'?window:null);
