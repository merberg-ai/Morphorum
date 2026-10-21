/* PS3 structured Prompt Studio composer. Offline metadata only, no implicit text changes. */
(function(root){
'use strict';
const copy=value=>JSON.parse(JSON.stringify(value));
const error=(code,message)=>({ok:false,code,message});
const schema=1;
const tagPattern=/<lora\s*:\s*([^:>]+?)\s*:\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*>/ig;
function blank(){return {schema_version:schema,blocks:[]};}
function normalize(value,maxFrames=1000000){
  if(value==null)return {ok:true,composer:blank()};
  if(typeof value!=='object'||Array.isArray(value)||value.schema_version!==schema||!Array.isArray(value.blocks)
      ||value.blocks.length>100)return error('FORMAT','Unsupported Prompt Studio composer version or block count.');
  const ids=new Set(),blocks=[];
  for(const raw of value.blocks){
    if(!raw||typeof raw!=='object'||typeof raw.id!=='string'||!/^[a-zA-Z0-9_-]{1,80}$/.test(raw.id)
      ||ids.has(raw.id))return error('ID','Invalid or repeated composer block ID.');
    ids.add(raw.id);
    if(!['global','frame'].includes(raw.scope)||!['positive','negative'].includes(raw.lane)||
       !['before','after'].includes(raw.placement)||!['text','lora'].includes(raw.kind)||
       typeof raw.enabled!=='boolean')return error('BLOCK','Invalid block scope, lane, placement or type.');
    if(raw.scope==='frame'&&(!Number.isInteger(raw.frame)||raw.frame<0||raw.frame>=maxFrames))
      return error('FRAME','Scene block frame is outside the animation timeline.');
    if(raw.scope==='global'&&raw.frame!==null)return error('FRAME','Global blocks cannot reference a specific frame.');
    const label=raw.label||'';
    if(typeof label!=='string'||label.length>120)return error('LABEL','Block label exceeds 120 characters.');
    const block={id:raw.id,scope:raw.scope,frame:raw.frame,lane:raw.lane,
      kind:raw.kind,placement:raw.placement,enabled:raw.enabled,label};
    if(raw.kind==='text'){
      if(typeof raw.text!=='string'||raw.text.length>32768)
        return error('TEXT','Text block must contain at most 32,768 characters.');
      block.text=raw.text;
    }else{
      if(raw.lane!=='positive')return error('LORA_LANE','LoRA directives are only valid in positive prompts.');
      if(typeof raw.model_id!=='string'||raw.model_id.length>128||
         typeof raw.name!=='string'||!raw.name.trim()||raw.name.length>140||
         /[:<>\r\n]/.test(raw.name)||typeof raw.family!=='string'||raw.family.length>24||
         !['sdxl','flux','zimage'].includes(raw.family)||typeof raw.weight!=='number'||
         !Number.isFinite(raw.weight)||raw.weight< -4||raw.weight>4)
        return error('LORA','LoRA name, family or weight is invalid.');
      if(!Array.isArray(raw.triggers)||raw.triggers.length>24||
         raw.triggers.some(word=>typeof word!=='string'||word.length>160||/[\r\n]/.test(word)))
        return error('TRIGGERS','Trigger words are invalid or too long.');
      block.model_id=raw.model_id;block.name=raw.name;block.family=raw.family;
      block.weight=raw.weight;block.triggers=copy(raw.triggers);
    }
    blocks.push(block);
  }
  return {ok:true,composer:{schema_version:schema,blocks}};
}
function change(composer,action,options,maxFrames){
  const parsed=normalize(composer,maxFrames);
  if(!parsed.ok)return parsed;
  const next=parsed.composer;
  if(action==='add'){next.blocks.push(copy(options));}
  else{
    const at=next.blocks.findIndex(b=>b.id===options.id);
    if(at<0)return error('NOT_FOUND','Composer block was not found.');
    if(action==='remove')next.blocks.splice(at,1);
    else if(action==='update')next.blocks[at]={...next.blocks[at],...options.patch,id:next.blocks[at].id};
    else if(action==='reorder'){
      const to=at+options.direction;
      if(!Number.isInteger(options.direction)||Math.abs(options.direction)!==1||
         to<0||to>=next.blocks.length)return error('ORDER','Block is already at the edge.');
      [next.blocks[to],next.blocks[at]]=[next.blocks[at],next.blocks[to]];
    }else return error('ACTION','Unknown composer operation.');
  }
  return normalize(next,maxFrames);
}
function names(text){return [...String(text).matchAll(tagPattern)].map(m=>m[1].trim().toLowerCase());}
function compile(composer,tracks,maxFrames,modelFamily){
  const parsed=normalize(composer,maxFrames);
  if(!parsed.ok)return parsed;
  if(!tracks?.positive?.keyframes||!tracks?.negative?.keyframes)
    return error('TRACKS','Import a Prompt Studio draft first.');
  const active=parsed.composer.blocks.filter(b=>b.enabled);
  const warnings=[],next=copy(tracks),changed=[];
  for(const b of active){
    if(b.kind==='lora'&&b.family!==modelFamily)
      return error('FAMILY','LoRA '+b.name+' is indexed under '+b.family+
        ', not the selected '+modelFamily+' family.');
    if(b.scope==='frame'&&!next[b.lane].keyframes.some(k=>k.frame===b.frame))
      return error('KEYFRAME','Add a '+b.lane+' keyframe at F'+b.frame+' before applying its scene block.');
  }
  for(const lane of ['positive','negative'])for(const point of next[lane].keyframes){
    const blocks=active.filter(b=>b.lane===lane&&(b.scope==='global'||b.frame===point.frame));
    const before=[],after=[],seen=new Set(names(point.value));
    for(const b of blocks){
      let value=b.text;
      if(b.kind==='lora'){
        const normalized=b.name.trim().toLowerCase();
        if(seen.has(normalized))warnings.push('Duplicate LoRA "'+b.name+'" at '+lane+' F'+point.frame);
        seen.add(normalized);
        value='<lora:'+b.name+':'+String(b.weight)+'>';
        if(b.triggers.length)value+=', '+b.triggers.filter(x=>x.trim()).join(', ');
      }
      if(value.trim())(b.placement==='before'?before:after).push(value.trim());
    }
    if(!before.length&&!after.length)continue;
    // Original prompt is one unchanged segment; only composed edges are joined.
    const result=[...before,point.value,...after].filter(Boolean).join(', ');
    if(result.length>32768)return error('LENGTH','Composed prompt exceeds 32,768 characters at '+lane+' F'+point.frame);
    if(result!==point.value){changed.push({lane,frame:point.frame,before:point.value,after:result});point.value=result;}
  }
  return {ok:true,tracks:next,changed,warnings:[...new Set(warnings)]};
}
function makeId(){return 'b'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,11);}
function mount({panel,getDraft,onChange,onCommit,onNotice}={}){
  if(!panel)throw Error('PS3 composer container missing.');
  let records=[],cached={},loading=false,selected=null,preview=null,busy=false,appliedKey='';
  const el=document.createElement('section');el.className='ps3-composer';
  el.innerHTML=`<div class="ps3-heading"><div><h3>Structured Prompt Composer</h3>
    <p class="muted">Arrange reusable blocks and indexed LoRAs. Nothing changes a prompt until you commit the preview to the Studio draft.</p></div>
    <button type="button" class="secondary-button compact" data-p3="library">Refresh local LoRAs</button></div>
    <div class="ps3-form">
      <label>Scope <select data-p3="scope"><option value="global">All keyframes</option><option value="frame">One scene keyframe</option></select></label>
      <label>Lane <select data-p3="lane"><option value="positive">Positive</option><option value="negative">Negative</option></select></label>
      <label>Frame <select data-p3="frame"></select></label>
      <label>Type <select data-p3="kind"><option value="text">Text block</option><option value="lora">Indexed LoRA</option></select></label>
      <label>Position <select data-p3="placement"><option value="before">Beginning</option><option value="after">End</option></select></label>
      <label>Label <input type="text" maxlength="120" data-p3="label" placeholder="Character, style, setting…"></label>
      <label data-p3="text-wrap" class="ps3-wide">Text <textarea data-p3="text" maxlength="32768" rows="3" placeholder="Reusable visual details…"></textarea></label>
      <div class="ps3-lora-controls ps3-wide" data-p3="lora-wrap" hidden>
        <label>Local LoRA <select data-p3="lora"></select></label>
        <label>Weight <input type="number" data-p3="weight" step="0.05" min="-4" max="4" value="1"></label>
        <label>Trigger words (editable, comma-separated) <input type="text" data-p3="triggers" placeholder="Optional training triggers"></label>
        <div data-p3="thumbnail" class="ps3-thumbnail"></div>
        <small data-p3="metadata" class="muted">Only indexed, same-family LoRAs. Cached Civitai metadata is optional.</small>
      </div>
      <button type="button" class="secondary-button compact" data-p3="add">Add Composer Block</button>
    </div>
    <p data-p3="status" class="muted" role="status" aria-live="polite">Import a Studio draft to create blocks.</p>
    <div data-p3="blocks" class="ps3-block-list"></div>
    <div class="ps3-actions">
      <button type="button" class="secondary-button compact" data-p3="preview">Preview Composed Prompts</button>
      <button type="button" class="primary-button compact" data-p3="commit" disabled>Commit Preview to Studio Draft</button>
    </div>
    <div data-p3="results" class="ps3-results" hidden aria-label="Composer exact prompt preview"></div>`;
  panel.appendChild(el);
  const q=k=>el.querySelector('[data-p3="'+k+'"]');
  const draft=()=>getDraft?.(),current=()=>draft()?.composer||blank();
  const message=(v,bad=false)=>{q('status').textContent=v;q('status').dataset.error=bad?'1':'0';onNotice?.(v,bad);};
  const clearPreview=()=>{preview=null;q('results').hidden=true;q('commit').disabled=true;appliedKey='';};
  function frames(){
    const d=draft();const lane=q('lane').value,where=q('frame'),before=where.value;
    where.replaceChildren();
    for(const p of d?.tracks?.[lane]?.keyframes||[]){
      const op=document.createElement('option');op.value=String(p.frame);op.textContent='Frame '+p.frame;
      where.appendChild(op);
    }
    if([...where.options].some(o=>o.value===before))where.value=before;
    where.disabled=q('scope').value!=='frame';
  }
  function selectLoRA(){
    const id=q('lora').value;selected=records.find(x=>x.id===id)||null;
    const entry=cached[id]||{};
    const words=Array.isArray(entry.trained_words)?entry.trained_words:[];
    q('triggers').value=words.join(', ');
    const thumb=q('thumbnail');thumb.replaceChildren();
    if(selected && root.MorphorumThumbnails?.create){
      const image=root.MorphorumThumbnails.create(selected.id,selected.name,'ps3-thumb');
      if(image)thumb.appendChild(image);
    }
    q('metadata').textContent=selected?
      (words.length?'Cached Civitai trained words (unverified): '+words.join(', '):
      'No cached trained words. You may enter your own; they are not verified triggers.'):
      'Choose an indexed LoRA from the active model family.';
  }
  async function refreshLibrary(){
    const d=draft();if(!d?.ok)return;
    const family=d.snapshot.context.model?.family||'';
    if(!['sdxl','flux','zimage'].includes(family)){message('Unsupported selected model family: '+family,true);return;}
    loading=true;refresh();const contextId=d.snapshot.projectId;
    try{
      const response=await fetch('/api/loras?family='+encodeURIComponent(family),{cache:'no-store'});
      const body=await response.json();
      if(!response.ok)throw Error(body.detail||'LoRA catalog unavailable.');
      if(draft()?.snapshot.projectId!==contextId)return;
      records=(body.loras||[]).filter(x=>x.family===family);
      cached={};
      // Reuse cached local metadata only, never initiate Civitai sync or an internet request.
      for(let i=0;i<records.length;i+=120){
        try{
          const cache=await fetch('/api/civitai/library-catalog',{method:'POST',
            headers:{'Content-Type':'application/json'},body:JSON.stringify({model_ids:records.slice(i,i+120).map(x=>x.id)})});
          if(cache.ok){const result=await cache.json();Object.assign(cached,result.entries||{});}
        }catch(_){/* Civitai caching disabled or unavailable: local LoRAs still usable. */}
      }
      if(draft()?.snapshot.projectId!==contextId)return;
      refresh();selectLoRA();
      message(records.length+' indexed '+family+' LoRA(s) available. Triggers are user-selected suggestions.');
    }catch(e){records=[];cached={};message('LoRA catalog: '+e.message,true);}
    finally{loading=false;refresh();}
  }
  function renderBlocks(){
    const host=q('blocks');host.replaceChildren();
    for(const [i,b] of current().blocks.entries()){
      const row=document.createElement('div');row.className='ps3-block';
      const summary=document.createElement('div');summary.className='ps3-block-summary';
      const title=document.createElement('strong');
      title.textContent=(b.kind==='lora'?'LoRA ':'')+(b.label||b.name||b.text.slice(0,40)||'Text');
      const meta=document.createElement('small');
      meta.textContent=b.scope==='global'?'All '+b.lane+' keyframes':
        b.lane+' F'+b.frame;
      const position=document.createElement('small');position.textContent=b.placement==='before'?'Beginning':'End';
      summary.append(title,meta,position);
      const buttons=document.createElement('div');buttons.className='ps3-block-controls';
      const toggle=document.createElement('label');toggle.textContent='Active';
      const checked=document.createElement('input');checked.type='checkbox';checked.checked=b.enabled;
      checked.addEventListener('change',()=>modify('update',{id:b.id,patch:{enabled:checked.checked}}));
      toggle.prepend(checked);buttons.appendChild(toggle);
      for(const [label,action,arg] of [['↑','reorder',-1],['↓','reorder',1],['Remove','remove',null]]){
        const button=document.createElement('button');button.type='button';
        button.className='secondary-button compact';button.textContent=label;
        if(action==='reorder'&&(i+arg<0||i+arg>=current().blocks.length))button.disabled=true;
        button.addEventListener('click',()=>modify(action,
          action==='reorder'?{id:b.id,direction:arg}:{id:b.id}));
        buttons.appendChild(button);
      }
      const editor=document.createElement('div');editor.className='ps3-block-editor';
      const positionChoice=document.createElement('select');
      positionChoice.setAttribute('aria-label','Block placement for '+(b.label||b.name||b.id));
      for(const [value,label] of [['before','Beginning'],['after','End']]){
        const option=document.createElement('option');option.value=value;
        option.textContent=label;positionChoice.appendChild(option);
      }
      positionChoice.value=b.placement;
      positionChoice.addEventListener('change',()=>modify('update',
        {id:b.id,patch:{placement:positionChoice.value}}));
      editor.appendChild(positionChoice);
      if(b.kind==='text'){
        const field=document.createElement('textarea');field.rows=2;
        field.maxLength=32768;field.value=b.text;
        field.setAttribute('aria-label','Text for '+(b.label||b.id));
        field.addEventListener('change',()=>modify('update',{id:b.id,patch:{text:field.value}}));
        editor.appendChild(field);
      }else{
        const weight=document.createElement('input');weight.type='number';weight.min='-4';
        weight.max='4';weight.step='.05';weight.value=String(b.weight);
        weight.setAttribute('aria-label','LoRA weight for '+b.name);
        weight.addEventListener('change',()=>modify('update',
          {id:b.id,patch:{weight:Number(weight.value)}}));
        const triggers=document.createElement('input');triggers.type='text';
        triggers.value=b.triggers.join(', ');
        triggers.setAttribute('aria-label','Trigger words for '+b.name);
        triggers.addEventListener('change',()=>modify('update',
          {id:b.id,patch:{triggers:triggers.value.split(',').map(x=>x.trim()).filter(Boolean)}}));
        editor.append(weight,triggers);
      }
      row.append(summary,buttons,editor);host.appendChild(row);
    }
  }
  function refresh(){
    const d=draft(),usable=Boolean(d?.ok&&!d.applied&&!busy),family=d?.snapshot?.context?.model?.family;
    panel.hidden=!usable;
    if(!usable)return;
    const isLoRA=q('kind').value==='lora';
    if(q('lane').value==='negative'&&isLoRA)q('kind').value='text';
    q('lora-wrap').hidden=q('kind').value!=='lora';
    q('text-wrap').hidden=q('kind').value==='lora';
    q('frame').disabled=q('scope').value!=='frame';
    const list=q('lora'),currentId=list.value;list.replaceChildren();
    for(const item of records.filter(x=>x.family===family)){
      const option=document.createElement('option');option.value=item.id;
      option.textContent=item.name||item.filename||item.id;list.appendChild(option);
    }
    if([...list.options].some(x=>x.value===currentId))list.value=currentId;
    if(selected&&[...list.options].some(x=>x.value===selected.id))list.value=selected.id;
    q('add').disabled=busy||loading||(q('kind').value==='lora'&&!list.value);
    q('preview').disabled=busy||!current().blocks.length;
    q('commit').disabled=busy||!preview;
    frames();renderBlocks();
  }
  function modify(action,options){
    const d=draft();
    const result=change(current(),action,options,d.snapshot.context.maxFrames);
    if(!result.ok){message(result.message,true);return;}
    clearPreview();const response=onChange?.(result.composer);
    if(response?.ok===false){message(response.message,true);return;}
    refresh();message('Composer blocks updated. Preview before committing changes to prompts.');
  }
  function add(){
    const d=draft();if(!d?.ok)return;
    const kind=q('kind').value,lane=q('lane').value,scope=q('scope').value;
    const block={id:makeId(),scope,lane,frame:scope==='global'?null:Number(q('frame').value),
      placement:q('placement').value,label:q('label').value,kind,enabled:true};
    if(kind==='text')block.text=q('text').value;
    else{
      const r=records.find(r=>r.id===q('lora').value);
      if(!r)return message('Select an indexed LoRA first.',true);
      block.name=(r.filename||r.name||'').replace(/\.(?:safetensors|pt|ckpt|pth)$/i,'');
      block.model_id=r.id;block.family=r.family;block.weight=Number(q('weight').value);
      block.triggers=q('triggers').value.split(',').map(x=>x.trim()).filter(Boolean).slice(0,24);
    }
    modify('add',block);
  }
  function previewText(){
    const d=draft();if(!d?.ok)return;
    const result=compile(current(),d.tracks,d.snapshot.context.maxFrames,
      d.snapshot.context.model?.family);
    if(!result.ok){message(result.message,true);clearPreview();return;}
    preview={...result,sourceRevision:d.revision,composerKey:JSON.stringify(current())};
    q('results').replaceChildren();
    const summary=document.createElement('p');
    summary.textContent=result.changed.length+' prompt keyframe(s) would change. '+
      (result.warnings.length?result.warnings.length+' warning(s). ':'')+
      'Original base text remains intact inside each composed result.';
    q('results').appendChild(summary);
    for(const warning of result.warnings){
      const notice=document.createElement('p');notice.className='ps3-warning';
      notice.textContent=warning;q('results').appendChild(notice);
    }
    for(const change of result.changed.slice(0,60)){
      const details=document.createElement('details');
      const head=document.createElement('summary');head.textContent=change.lane+' F'+change.frame;
      const before=document.createElement('pre');before.textContent='Before: '+change.before;
      const after=document.createElement('pre');after.textContent='After: '+change.after;
      details.append(head,before,after);q('results').appendChild(details);
    }
    q('results').hidden=false;q('commit').disabled=result.changed.length===0;
    message('Review exact composed prompt text before committing to the Studio draft.');
  }
  async function commit(){
    const d=draft(),p=preview;
    if(!d?.ok||!p||d.revision!==p.sourceRevision||
       JSON.stringify(current())!==p.composerKey)
      return message('Composer preview is stale. Preview again.',true);
    if(!p.changed.length)return;
    if(p.warnings.length){
      if(!root.MorphorumDialog?.confirm)
        return message('Confirmation unavailable; duplicate warnings were not accepted.',true);
      const proceed=await root.MorphorumDialog.confirm({
        title:'Commit composed prompts with warnings?',
        message:p.warnings.join('\n').slice(0,850)+'\nThese changes affect only the Studio draft until Apply to Animation.',
        confirmText:'Commit to Draft',cancelText:'Keep Editing'});
      if(!proceed)return;
    }
    // Second commit of unchanged blocks would append them twice. Require a new block edit
    // or a new import after the first explicit commit.
    if(appliedKey===p.composerKey)return message('Composer already committed; edit blocks before another preview.',true);
    const result=onCommit?.(p.tracks);
    if(result?.ok===false)return message(result.message,true);
    appliedKey=p.composerKey;preview=null;q('results').hidden=true;q('commit').disabled=true;
    message('Composed text committed to the Studio draft. Review timeline diff before Apply to Animation.');
  }
  q('library').addEventListener('click',()=>void refreshLibrary());
  q('scope').addEventListener('change',frames);
  q('lane').addEventListener('change',()=>{frames();refresh();});
  q('kind').addEventListener('change',refresh);
  q('lora').addEventListener('change',selectLoRA);
  q('add').addEventListener('click',add);
  q('preview').addEventListener('click',previewText);
  q('commit').addEventListener('click',()=>void commit());
  panel.hidden=true;
  return {refresh,reset(){selected=null;records=[];cached={};preview=null;appliedKey='';
      panel.hidden=!draft()?.ok;refresh();if(draft()?.ok)void refreshLibrary();},
    invalidate(){preview=null;q('results').hidden=true;q('commit').disabled=true;},
    getPreview:()=>preview};
}
const api={blank,normalize,change,compile,mount};
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.MorphorumPromptStudioComposer=api;
})(typeof window==='object'?window:null);
