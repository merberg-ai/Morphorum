(() => {
  'use strict';
  const KEY = 'X-Morphorum-Setup';
  const OPTIONS = ['gentle-dolly-in','gentle-dolly-out'];
  let generation = 0;
  let chosen = 'gentle-dolly-in';
  let modelId = '';
  let models = [];
  let catalog = null;
  let busy = false;
  let choicesReady = false;

  const node = (tag, cls, value) => {
    const el = document.createElement(tag);
    if(cls) el.className=cls;
    if(value !== undefined) el.textContent=value;
    return el;
  };
  function leave() { generation++; busy=false; choicesReady=false; }
  async function api(url, options={}) {
    const response=await fetch(url, {cache:'no-store',...options});
    const result=await response.json();
    if(!response.ok) throw new Error(String(result.detail||'Request failed'));
    return result;
  }
  function selection() {
    if(!choicesReady) throw new Error('Starter examples are not ready. Check the catalog error and refresh setup.');
    return {template_id:chosen,model_id:modelId};
  }
  function selectionFrom(snapshot) {
    const id=snapshot?.example_template_id;
    chosen=OPTIONS.includes(id)?id:'gentle-dolly-in';
    modelId=String(snapshot?.example_model_id||'');
  }
  function warning(container,message) {
    const p=node('p','first-run-example-warning',message);
    p.setAttribute('role','status');
    container.appendChild(p);
    return p;
  }
  async function fetchOptions() {
    const [examples, index]=await Promise.all([
      api('/api/setup/examples'),api('/api/models?limit=2000'),
    ]);
    if(!Array.isArray(examples.examples)||examples.examples.length!==2 ||
       examples.examples.some((e,i)=>e.id!==OPTIONS[i]))
      throw Error('Example catalog does not contain the expected two presets.');
    catalog=examples;
    models=(index.models||[]).filter(m=>m.kind==='checkpoints');
  }
  function renderChoices(host, locked=false) {
    const cards=node('div','first-run-example-cards');
    const group=node('div','first-run-example-choice-group');
    group.setAttribute('role','group');
    group.setAttribute('aria-label','Choose starter animation');
    const buttons=[];
    catalog.examples.forEach(example=>{
      const b=node('button','first-run-example-card');
      b.type='button';
      b.disabled=locked;
      b.setAttribute('aria-pressed',String(chosen===example.id));
      const heading=node('strong','',example.name);
      const description=node('span','',example.description);
      const spec=node('small','','3D Camera Z · 512 × 512 · 48 frames · 12 FPS · 4 seconds');
      b.append(heading,description,spec);
      b.addEventListener('click',()=>{
        chosen=example.id;
        buttons.forEach((button,index)=>
          button.setAttribute('aria-pressed',String(catalog.examples[index].id===chosen)));
      });
      group.appendChild(b);buttons.push(b);
    });
    cards.appendChild(group);
    host.appendChild(cards);
    const label=node('label','first-run-example-model-label','Base generation model');
    const select=node('select','first-run-example-model');
    const none=node('option','','No model yet (create editable project)');
    none.value='';
    select.appendChild(none);
    models.forEach(model=>{
      const option=node('option','', '['+model.family.toUpperCase()+'] '+model.name);
      option.value=model.id;
      select.appendChild(option);
    });
    if(!models.some(model=>model.id===modelId)) modelId='';
    select.value=modelId;
    select.disabled=locked;
    select.addEventListener('change',()=>{modelId=select.value;});
    label.appendChild(select);
    host.appendChild(label);
    warning(host,'You can create and open the project without a model. Rendering requires an indexed, compatible base checkpoint. Downloading weights is optional; this does not start a render.');
    const prompt=node('p','first-run-note',
      'Both examples use the same alpine-cabin scene and fixed seed. Positive Camera Z pushes in; negative Camera Z pulls out. All other camera axes stay at zero. Preview Camera Motion before generating.');
    host.appendChild(prompt);
  }
  async function showExamples(host, snapshot, {onReady}={}) {
    leave();const token=generation;
    onReady?.(false);
    selectionFrom(snapshot);
    const title=node('h3','', 'Choose a four-second camera move');
    host.appendChild(title);
    warning(host,'Loading examples and installed checkpoints…');
    try {
      await fetchOptions();
      if(token!==generation)return;
      host.replaceChildren(title);
      renderChoices(host,Boolean(snapshot?.example_project_id));
      choicesReady=true;
      onReady?.(true);
      if(snapshot?.example_project_id) warning(host,
        'A starter project has already been reserved for this setup. It will be reused, not overwritten.');
    } catch(error) {
      if(token===generation) {
        choicesReady=false;
        onReady?.(false);
        host.replaceChildren(title);
        warning(host,'Could not load the example catalog: '+error.message);
      }
    }
  }
  async function showFinish(host,snapshot,{reserved,complete,openEditor,toast,manual}) {
    leave();const token=generation;
    selectionFrom(snapshot);
    host.appendChild(node('h3','','Review first-run example'));
    const status=warning(host,'Checking project and model setup…');
    let folders='Folder settings not available';
    let zimage='Managed Z-Image status unavailable';
    let zimageReady=false;
    let index=[];
    try {
      const [settings,managed,indexData]=await Promise.all([
        api('/api/settings'),api('/api/managed-models/zimage-turbo'),
        api('/api/models?limit=2000'),
      ]);
      if(token!==generation)return;
      const configured=settings.settings?.models||{};
      const families=['sdxl','flux','zimage'];
      const dirs=families.flatMap(family=>['checkpoints','loras'].map(kind=>{
        const paths=configured?.[family]?.[kind];
        return Array.isArray(paths) && paths.length
          ? family.toUpperCase()+' '+kind+': '+paths.length+' configured' : null;
      }).filter(Boolean));
      folders=dirs.length?dirs.join(' · '):'No checkpoint or LoRA folders configured';
      zimageReady=managed.installed===true && managed.status==='installed';
      zimage=managed.installed?'Z-Image verified installed':
        managed.status==='downloading'?'Z-Image downloading (not ready)':
        'Z-Image: '+(managed.status||'not installed');
      index=(indexData.models||[]).filter(m=>m.kind==='checkpoints');
    } catch(error) {
      if(token!==generation)return;
      warning(host,'Some status checks failed: '+error.message);
    }
    if(token!==generation)return;
    const details=node('dl','first-run-example-summary');
    for(const [key,value] of [
      ['Starter',chosen==='gentle-dolly-out'?'Gentle Dolly Out':'Gentle Dolly In'],
      ['Motion','3D native Camera Z · 48 frames at 12 FPS · 512 × 512'],
      ['Folders',folders],
      ['Managed model',zimage],
      ['Base model',index.find(m=>m.id===modelId)?.name||'None selected'],
    ]) {
      const line=node('div');
      line.append(node('dt','',key),node('dd','',value));
      details.appendChild(line);
    }
    host.appendChild(details);
    const indexedModel=Boolean(index.find(m=>m.id===modelId));
    const pendingManaged=modelId==='managed:zimage-turbo' && !zimageReady;
    const missingSelected=Boolean(modelId) && !indexedModel;
    const hasModel=indexedModel && !pendingManaged;
    status.textContent=missingSelected
      ? 'The previously selected checkpoint is no longer indexed. Return to Example Animations to select another model or choose No model yet.'
      : pendingManaged
        ? 'The selected managed Z-Image package is not yet verified. Return to Example Animations and choose No model yet (editable project), or finish its download before creating.'
      : hasModel
        ? 'Ready to create an editable project with the selected model. Rendering will not start.'
        : 'No usable base model selected. The example can be created, opened and edited, but is NOT render-ready. Select/download a model before generating.';
    const actions=node('div','first-run-example-actions');
    const create=node('button','primary-button','Create Example & Open Editor');
    const without=node('button','secondary-button','Finish Without Example');
    const change=node('button','secondary-button','Configure Model First');
    create.type=without.type=change.type='button';
    if(pendingManaged || missingSelected) create.disabled=true;
    const error=node('p','first-run-example-error');
    error.setAttribute('role','alert');error.hidden=true;
    async function perform(fn) {
      if(busy)return;
      busy=true;
      create.disabled=without.disabled=change.disabled=true;
      error.hidden=true;
      try {await fn();}
      catch(err) {
        if(token===generation){error.hidden=false;error.textContent=err.message;
          toast?.('First-run setup',err.message,'error');}
      } finally {
        busy=false;
        if(token===generation) {create.disabled=pendingManaged||missingSelected;without.disabled=change.disabled=false;}
      }
    }
    create.addEventListener('click',()=>void perform(async()=>{
      if(!hasModel && !(await window.MorphorumDialog?.confirm?.({
        title:'Create example without a model?',
        message:'This project will open in the editor but cannot render until you select a compatible checkpoint. Continue?',
        confirmText:'Create Editable Project',
      })))return;
      const result=await api('/api/setup/example',{
        method:'POST',
        headers:{'Content-Type':'application/json',[KEY]:'1'},
        body:JSON.stringify({
          template_id:chosen,model_id:modelId,
          revision:snapshot.revision,
          manual:Boolean(manual),
        }),
      });
      if(token!==generation)return;
      reserved(result.revision,result.project?.id);
      snapshot.revision=result.revision;
      const opened=await openEditor(result.project.id);
      if(!opened) throw Error('The example was saved but the Project Editor could not open it. Retry to open the same saved project, without creating another.');
      await complete();
    }));
    without.addEventListener('click',()=>void perform(async()=>await complete({without_example:true})));
    change.addEventListener('click',()=>window.MorphorumFirstRunSetup?.goto('models'));
    actions.append(create,without,change);
    host.append(actions,error);
    if(snapshot.example_project_id) {
      const note=node('p','first-run-note',
        'Previously saved example: '+snapshot.example_project_id+
        '. Opening it again will keep any edits and will not create a duplicate.');
      host.appendChild(note);
    }
  }
  window.MorphorumSetupExamples={showExamples,showFinish,leave,selection};
})();
