/* PS5.3: opt-in serial Ollama prompt comparison, with human/physical review. */
(function(root){
  'use strict';
  const CASES=[
    {id:'horror',name:'Battlefield horror',mode:'create',count:3,
      idea:'Three continuous cinematic scenes of a fictional devastated WWII-era battlefield: an undead skeletal soldier emerges through fog, reaches an empty trench, then stands near a ruined city. Preserve a realistic gas mask with exactly two symmetrical eyepieces and one central filter. Vary composition and lighting without changing the soldier.',
      subject:'The same skeletal soldier with a rusted helmet, two-eyepiece gas mask and torn greatcoat.',
      style:'Desaturated cinematic horror, fog, believable perspective, detailed environment.'},
    {id:'character',name:'Recurring character',mode:'create',count:3,
      idea:'Three connected shots of a gray alien in colorful floral shorts and flip-flops examining a CRT television in a cluttered 1990s living room. The alien approaches the screen, tries the remote, then reacts to the flickering display. Preserve costume and anatomy across each view.',
      subject:'The same small gray alien with large black eyes, colorful floral shorts and flip-flops.',
      style:'Photorealistic 1990s interior with warm practical lights and analog video texture.'},
    {id:'landscape',name:'Landscape progression',mode:'create',count:3,
      idea:'Three related widescreen scenes showing dawn above one flooded post-industrial city: distant skyline, flooded boulevard with trams, rooftop panorama as the sun emerges. Preserve the same clock tower, bridges and sunrise direction.',
      subject:'The same flooded post-industrial city with a clock tower and two elevated rail bridges.',
      style:'Detailed cinematic matte painting, coherent scale, muted sunrise and light haze.'},
    {id:'mixed-lora',name:'Mixed-LoRA refinement (synthetic)',mode:'refine',count:2,
      idea:'Refine two existing scenes of a masked explorer holding a brass lantern in a ruined train station, then walking onto a foggy platform. Keep physical identity, costume, visual direction and scene continuity. The illustrative LoRA tags and weights belong to the application, not the model; do not invent adapters.',
      subject:'The same masked explorer in a dark olive coat holding a brass lantern.',
      style:'Rainy graphic novel with ink-work and a restrained nocturnal palette.',
      positive:[
        {frame:0,value:'<lora:EvalInkStyle:0.65> masked explorer in derelict station'},
        {frame:48,value:'<lora:EvalInkStyle:0.65> <lora:EvalAtmosphere:0.35> explorer on foggy platform'}]}
  ];
  const byId=Object.fromEntries(CASES.map(c=>[c.id,c]));
  const clone=x=>JSON.parse(JSON.stringify(x));
  function makeRequest(caseId,family,model,endpoint,allowLan){
    const c=byId[caseId];
    if(!c||!['sdxl','flux','zimage'].includes(family)||!model)
      throw Error('Select a valid case, model and project model family.');
    return {endpoint,allow_lan:allowLan===true,model,mode:c.mode,idea:c.idea,
      scene_count:c.count,family,max_frames:96,fps:24,include_negative:false,
      profile:'ps5-'+family+'-v1',target_frame:null,
      continuity:{subject:c.subject,style:c.style},
      tracks:{positive:{kind:'prompt',interpolation:'blend',
        keyframes:clone(c.positive||[{frame:0,value:'Baseline scene prompt'}])},
        negative:{kind:'prompt',interpolation:'hold',
          keyframes:[{frame:0,value:'unwanted artifacts'}]}}};
  }
  function validateResult(value,request){
    const expected=request.mode==='refine'?[0,48]:[0,32,64];
    if(!value||value.provenance?.provider!=='ollama'||
       value.provenance.model!==request.model||value.provenance.family!==request.family||
       value.provenance.mode!==request.mode||!Array.isArray(value.scenes)||
       value.scenes.length!==expected.length||
       value.scenes.some((x,i)=>x.frame!==expected[i]||
         typeof x.positive!=='string'||x.positive.length>4000)||
       !Array.isArray(value.tracks?.positive?.keyframes)||
       value.tracks.positive.keyframes.length!==expected.length||
       value.tracks.positive.keyframes.some((x,i)=>x.frame!==expected[i]||typeof x.value!=='string'))
      throw Error('Candidate returned a malformed or mismatched evaluation proposal.');
    return {scenes:clone(value.scenes),tracks:clone(value.tracks),
      diagnostics:clone(value.diagnostics||[]),warnings:clone(value.warnings||[]),
      metrics:clone(value.metrics||{})};
  }
  function mount({container,getContext,readStream,onBusy}={}){
    if(!container||!getContext||!readStream)throw Error('Missing PS5.3 provider integration.');
    container.innerHTML=[
      '<fieldset class="ps53-panel"><legend>PS5.3 · Compare local Ollama models</legend>',
      '<p class="muted">Run a fixed test through two installed models, <b>one after another</b>.',
      ' Outputs remain separate from the current Studio draft. No project prompts,',
      ' start images or audio are sent. No automatic winner or fake image-quality score.</p>',
      '<div class="ps53-fields">',
      '<label>Test case <select data-ev="case"></select></label>',
      '<label>Candidate A <select data-ev="a"></select></label>',
      '<label>Candidate B <select data-ev="b"></select></label></div>',
      '<p class="muted" data-ev="details"></p>',
      '<div class="ps4-actions">',
      '<button class="primary-button compact" data-ev="run" type="button">Compare Models</button>',
      '<button class="secondary-button compact" data-ev="cancel" type="button" disabled>Cancel Comparison</button>',
      '<button class="secondary-button compact" data-ev="export" type="button" disabled>Export JSON Report</button>',
      '</div><p class="ps4-status" role="status" data-ev="status" aria-live="polite">',
      'Connect Ollama and choose two models.</p>',
      '<div class="ps53-results" data-ev="results"></div>',
      '<p class="muted">Rate prompt fidelity and continuity yourself. For a physical spot-check,',
      ' render selected prompts using identical checkpoint, seed, settings and compatible',
      ' installed LoRAs, then record the outcome. Synthetic benchmark LoRA names are not real',
      ' adapter files. Text tests alone never establish render quality or GPU speed.</p>',
      '</fieldset>'
    ].join('');
    const q=k=>container.querySelector('[data-ev="'+k+'"]');
    for(const c of CASES){
      const op=document.createElement('option');op.value=c.id;op.textContent=c.name;
      q('case').appendChild(op);
    }
    let busy=false,abort=null,seq=0,report=null,sourceKey='',modelKey='';
    function notice(s,bad=false){q('status').textContent=s;q('status').dataset.error=bad?'1':'0';}
    function clear(){report=null;q('results').replaceChildren();q('export').disabled=true;}
    function fill(models){
      const old=[q('a').value,q('b').value];
      for(const key of ['a','b']){
        const select=q(key);select.replaceChildren();
        for(const m of models){
          const o=document.createElement('option');o.value=m.name;
          o.textContent=m.name+(m.parameter_size?' · '+m.parameter_size:'');
          select.appendChild(o);
        }
      }
      q('a').value=models.some(x=>x.name===old[0])?old[0]:(models[0]?.name||'');
      q('b').value=models.some(x=>x.name===old[1])?old[1]:(models[1]?.name||'');
    }
    function validContext(ctx){
      return Boolean(ctx?.draft?.ok&&!ctx.draft.applied&&ctx.connected&&!ctx.parentBusy&&
        ctx.models?.length>=2&&q('a').value!==q('b').value&&
        ctx.models.some(x=>x.name===q('a').value)&&ctx.models.some(x=>x.name===q('b').value));
    }
    function refresh(){
      const ctx=getContext(),key=(ctx?.draft?.snapshot?.projectId||'')+'|'+
        (ctx?.draft?.snapshot?.context?.model?.family||'');
      if(key!==sourceKey){sourceKey=key;clear();}
      const modelSignature=JSON.stringify((ctx?.models||[]).map(x=>[x.name,x.parameter_size]));
      if(!busy&&modelSignature!==modelKey){
        modelKey=modelSignature;fill(ctx?.models||[]);clear();
      }
      q('details').textContent=q('case').value==='mixed-lora'?
        'Refinement of frames 0 and 48 with synthetic LoRA tags; no installed LoRA is loaded.':
        'Fixed 24 FPS test, three keyframes at frames 0, 32, 64.';
      q('run').disabled=busy||!validContext(ctx);
      q('cancel').disabled=!busy;
      q('export').disabled=busy||!report;
      for(const key of ['case','a','b'])q(key).disabled=busy||ctx?.parentBusy;
    }
    function scoreControl(item,title,key,options){
      const wrapper=document.createElement('label');wrapper.className='ps53-grade';
      wrapper.append(document.createTextNode(title+' '));
      const selector=document.createElement('select');
      for(const [value,label] of options){
        const option=document.createElement('option');option.value=value;option.textContent=label;
        selector.appendChild(option);
      }
      selector.value=item[key]||'';
      selector.addEventListener('change',()=>{item[key]=selector.value;});
      wrapper.appendChild(selector);return wrapper;
    }
    function show(){
      q('results').replaceChildren();if(!report)return;
      for(const item of report.candidates){
        const article=document.createElement('article');article.className='ps53-candidate';
        const header=document.createElement('h4');header.textContent=item.model;
        article.appendChild(header);
        const metric=document.createElement('p');metric.className='muted';
        if(item.error)metric.textContent='Error: '+item.error;
        else if(item.output){
          metric.textContent='Elapsed '+item.elapsed_seconds+'s · Ollama evaluation '+
            (item.output.metrics.eval_seconds??'unavailable')+'s · '+ 
            (item.output.metrics.eval_count??'?')+' output tokens (reported)';
        }else metric.textContent='No completed result';
        article.appendChild(metric);
        if(item.output){
          for(const scene of item.output.scenes){
            const detail=document.createElement('details');detail.open=true;
            const s=document.createElement('summary');s.textContent='Frame '+scene.frame+' · '+(scene.title||'Scene');
            const pre=document.createElement('pre');pre.textContent=scene.positive;
            detail.append(s,pre);article.appendChild(detail);
          }
          const copyButton=document.createElement('button');
          copyButton.type='button';copyButton.className='secondary-button compact';
          copyButton.textContent='Copy Prompts for Render Spot-check';
          copyButton.addEventListener('click',()=>{
            const text=item.output.scenes.map(s=>'Frame '+s.frame+':\n'+s.positive).join('\n\n');
            if(root.navigator?.clipboard?.writeText)
              void root.navigator.clipboard.writeText(text).then(
                ()=>notice('Candidate prompts copied.'),
                ()=>notice('Clipboard denied. Export JSON instead.',true));
            else notice('Clipboard unavailable. Export JSON instead.',true);
          });
          article.appendChild(copyButton);
        }
        const grades=document.createElement('div');grades.className='ps53-ratings';
        const ratings=[['','Not rated'],['1','1 · poor'],['2','2 · weak'],
          ['3','3 · adequate'],['4','4 · good'],['5','5 · excellent']];
        grades.append(scoreControl(item,'Instruction fidelity (human)','fidelity',ratings));
        grades.append(scoreControl(item,'Scene continuity (human)','continuity',ratings));
        grades.append(scoreControl(item,'Prompt clarity (human)','clarity',ratings));
        grades.append(scoreControl(item,'Physical render spot-check','render_check',[
          ['','Not tested'],['pass','Pass'],['concern','Visual concern'],['fail','Render failed']]));
        article.appendChild(grades);q('results').appendChild(article);
      }
    }
    async function run(){
      const ctx=getContext();
      if(busy||!validContext(ctx))return;
      const draft=ctx.draft,id=draft.snapshot.projectId,revision=draft.revision;
      const family=draft.snapshot.context.model.family,chosen=q('case').value;
      const names=[q('a').value,q('b').value];
      const requests=names.map(n=>makeRequest(chosen,family,n,ctx.endpoint,ctx.allowLan));
      clear();
      report={schema_version:1,format:'morphorum-ps53-evaluation',
        created_at:new Date().toISOString(),family,case_id:chosen,
        test_input:clone(requests[0]),candidates:[]};
      // Do not export the configured Ollama endpoint or network consent.
      delete report.test_input.endpoint;delete report.test_input.allow_lan;
      busy=true;const token=++seq;abort=new AbortController();onBusy?.(true);refresh();
      try{
        for(let i=0;i<requests.length;i++){
          if(token!==seq||abort.signal.aborted)break;
          const model=names[i],start=Date.now();
          const item={model,elapsed_seconds:0,error:null,output:null,
            fidelity:'',continuity:'',clarity:'',render_check:''};
          report.candidates.push(item);
          notice('Candidate '+(i+1)+'/2 · '+model+' · connecting to Ollama…');
          try{
            const response=await fetch('/api/prompt-studio/ollama/generate-stream',{
              method:'POST',cache:'no-store',signal:abort.signal,
              headers:{'Content-Type':'application/json'},body:JSON.stringify(requests[i])});
            if(!response.ok){
              const err=await response.json().catch(()=>({}));
              throw Error(err.detail||'Ollama HTTP '+response.status);
            }
            const result=await readStream(response,event=>{
              if(token===seq&&event.type==='progress')
                notice('Candidate '+(i+1)+'/2 · '+model+' · '+
                  String(event.message||event.stage||'waiting')+' · '+
                  (event.elapsed_seconds??'?')+'s');
            });
            if(token!==seq)break;
            item.output=validateResult(result,requests[i]);
          }catch(error){
            if(token!==seq||error.name==='AbortError')break;
            item.error=String(error.message||error).slice(0,350);
          }finally{item.elapsed_seconds=Math.round((Date.now()-start)/1000);}
          if(token!==seq||abort.signal.aborted)break;
          const current=getContext().draft;
          if(current!==draft||draft.revision!==revision||
             current?.snapshot?.projectId!==id){
            clear();notice('Studio draft/project changed; stale comparison discarded.',true);
            break;
          }
          show();
        }
        if(token===seq&&report)
          notice('Comparison attempts completed. Manually review, score and render representative prompts.');
      }finally{
        if(token===seq){busy=false;abort=null;onBusy?.(false);refresh();}
      }
    }
    function cancel(){
      if(!busy)return;
      ++seq;abort?.abort();abort=null;busy=false;clear();
      onBusy?.(false);notice('Comparison cancelled. Partial results discarded.');
      refresh();
    }
    function reset(){cancel();clear();sourceKey='';modelKey='';refresh();}
    function exportReport(){
      if(!report||busy)return;
      const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
      const url=URL.createObjectURL(blob),anchor=document.createElement('a');
      anchor.href=url;anchor.download='morphorum-ps53-'+report.family+'-'+report.case_id+'.json';
      document.body.appendChild(anchor);anchor.click();anchor.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    q('run').addEventListener('click',()=>void run());
    q('cancel').addEventListener('click',cancel);
    q('export').addEventListener('click',exportReport);
    for(const key of ['case','a','b'])q(key).addEventListener('change',()=>{clear();refresh();});
    refresh();
    return {refresh,reset,cancel,isBusy:()=>busy};
  }
  const api={CASES,makeRequest,validateResult,mount};
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MorphorumPromptStudioEvaluation=api;
})(typeof window==='object'?window:null);
