/* PS1.3: manual Prompt Studio workspace. No saves, renders, AI or audio writes. */
(function(root) {
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  const problem=(code,message)=>({ok:false,code,message});
  function beginDraft(snapshot,bridge) {
    if(!snapshot?.ok || !snapshot.projectId || !bridge)
      return problem('NO_SNAPSHOT','Import a current Project Editor snapshot first.');
    const maxFrames=Number(snapshot.context?.maxFrames);
    const validation=bridge.validateTracks(snapshot.promptTracks,maxFrames);
    if(!validation.ok) return validation;
    return {ok:true,snapshot:clone(snapshot),original:clone(validation.tracks),
      tracks:clone(validation.tracks),revision:0,applied:false};
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
  function mount({panel,onEditor}={}) {
    if(!panel) throw new Error('Prompt Studio panel is required.');
    const bridge=root.MorphorumPromptStudioBridge;
    let draft=null,busy=false,invalid=false,previewedRevision=-1,blocked=false;
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
      <div class="ps13-context" data-ps="context">No prompts imported. Open a project in Project Editor, then select Import Existing Prompts.</div>
      <p class="ps13-notice muted">Import is read-only. This draft stays in browser memory until you reload. Apply changes only the UNSAVED Project Editor; Save Project there to persist them. Keyframe drag/snap, LLM authoring and audio storyboard sync come in later phases.</p>
      <p class="ps13-status" data-ps="status" role="status" aria-live="polite">Ready to import.</p>
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
      applyButton.disabled=!can||invalid||blocked||previewedRevision!==draft?.revision||count()===0;
      lanes.querySelectorAll('button,input,textarea,select').forEach(el=>{
        el.disabled=!can||el.dataset.psFixed==='1';
      });
    }
    function onEdit(result,redraw=false){
      if(!result.ok){invalid=true;status(result.message,true);controls();return;}
      invalid=false;blocked=false;previewClear();
      status(count()+' staged change(s). Preview Changes before applying.');
      if(redraw)renderLanes();
      else controls();
    }
    function makeLane(name){
      const track=draft.tracks[name];
      const section=document.createElement('section');
      section.className='ps13-lane';
      const heading=document.createElement('div');heading.className='ps13-lane-heading';
      const title=document.createElement('h3');title.textContent=name==='positive'?'Positive prompts':'Negative prompts';
      const modeLabel=document.createElement('label');modeLabel.textContent='Transition ';
      const mode=document.createElement('select');
      mode.setAttribute('aria-label',name+' prompt transition');
      for(const option of ['blend','hold']){
        const opt=document.createElement('option');opt.value=option;
        opt.textContent=option==='blend'?'Blend':'Hold';mode.appendChild(opt);
      }
      mode.value=track.interpolation;
      mode.addEventListener('change',()=>onEdit(updateDraft(draft,bridge,name,'interpolation',0,mode.value)));
      modeLabel.appendChild(mode);heading.append(title,modeLabel);
      section.appendChild(heading);
      const rows=document.createElement('div');rows.className='ps13-rows';
      for(const point of track.keyframes){
        const row=document.createElement('div');row.className='ps13-row';
        const frameLabel=document.createElement('label');frameLabel.textContent='Frame';
        const frame=document.createElement('input');frame.type='number';
        frame.min='0';frame.max=String(draft.snapshot.context.maxFrames-1);
        frame.step='1';frame.value=String(point.frame);
        frame.dataset.psFixed=point.frame===0?'1':'0';
        frame.disabled=point.frame===0;
        frame.setAttribute('aria-label',name+' keyframe '+point.frame+' frame');
        frame.addEventListener('change',()=>{
          const result=updateDraft(draft,bridge,name,'move',point.frame,frame.value);
          if(!result.ok)frame.value=String(point.frame);
          onEdit(result,true);
        });frameLabel.appendChild(frame);
        const textLabel=document.createElement('label');textLabel.textContent='Prompt at F'+point.frame;
        const textarea=document.createElement('textarea');textarea.rows=3;textarea.value=point.value;
        textarea.maxLength=32768;
        textarea.placeholder=name==='positive'?'Describe this scene…':'Avoid these visual elements…';
        textarea.setAttribute('aria-label',name+' prompt at frame '+point.frame);
        textarea.addEventListener('input',()=>onEdit(updateDraft(draft,bridge,name,'text',point.frame,textarea.value)));
        textLabel.appendChild(textarea);
        const remove=document.createElement('button');remove.type='button';
        remove.className='secondary-button compact';remove.textContent='Remove';
        remove.dataset.psFixed=point.frame===0?'1':'0';
        remove.disabled=point.frame===0;
        remove.addEventListener('click',()=>onEdit(updateDraft(draft,bridge,name,'remove',point.frame),true));
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
      add.addEventListener('click',()=>onEdit(updateDraft(draft,bridge,name,'add',at.value),true));
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
        draft=result;invalid=false;blocked=false;previewClear();showContext();renderLanes();
        status('Imported '+(draft.tracks.positive.keyframes.length+draft.tracks.negative.keyframes.length)+
          ' original keyframes. Editing here does not change Project Editor.');
      } catch(error){status(error.message||String(error),true);}
      finally{busy=false;controls();}
    }
    function reset(){
      if(!draft?.ok||draft.applied)return;
      draft.tracks=clone(draft.original);draft.revision+=1;
      invalid=false;blocked=false;previewClear();renderLanes();
      status('Prompt Studio draft restored to the imported prompts. Project Editor unchanged.');
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
      if(!draft?.ok||invalid||busy||previewedRevision!==draft.revision||blocked)return;
      busy=true;controls();
      status('Confirm the prompt-only transfer to Project Editor…');
      try {
        const result=await root.MorphorumAnimation?.applyPromptStudioTransfer?.(draft.snapshot,draft.tracks);
        if(!result?.ok){blocked=result?.code!=='CANCELLED';status(result?.message||'Apply failed.',true);return;}
        if(result.applied){
          draft.applied=true;previewClear();renderLanes();
          status('Prompts staged in Project Editor. Save Project there to persist.');
          onEditor?.();
        }else status(result.message||'No prompt changes to apply.');
      }catch(error){status(error.message||String(error),true);}
      finally{busy=false;controls();}
    }
    find('editor').addEventListener('click',()=>onEditor?.());
    importButton.addEventListener('click',()=>void importPrompts());
    resetButton.addEventListener('click',reset);
    previewButton.addEventListener('click',()=>void preview());
    applyButton.addEventListener('click',()=>void apply());
    controls();
    return {getState:()=>draft?{projectId:draft.snapshot.projectId,
      applied:draft.applied,changes:count(),revision:draft.revision}:null,
      onShow:()=>{if(!draft)status('Import Existing Prompts reads the open Project Editor, including its unsaved prompt text.');}};
  }
  const api={beginDraft,updateDraft,changeList,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioWorkspace=api;
})(typeof window==='object'?window:null);
