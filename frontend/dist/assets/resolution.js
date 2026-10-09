(() => {
  'use strict';
  // Shared UI-only presets. The backend still validates output dimensions.
  const divisorForFamily = family => ['flux','zimage'].includes(family) ? 16 : 8;
  const align = (value,divisor) => Math.max(64, Math.round(Number(value)/divisor)*divisor);
  const valueFor = (w,h) => w+'x'+h;
  function optionsFor(capability={}, family='') {
    const list=[],seen=new Set(),divisor=divisorForFamily(family);
    function add(group,label,w,h,video=false) {
      const originalW=Number(w),originalH=Number(h);
      if (!Number.isFinite(originalW)||!Number.isFinite(originalH)) return;
      const width=align(originalW,divisor),height=align(originalH,divisor);
      if (width>4096||height>4096) return;
      const value=valueFor(width,height);
      if (seen.has(value)) return;
      seen.add(value);
      const pixels=width*height;
      const suffix=(video&&(originalW!==width||originalH!==height)?' · model-aligned':'')+
        (pixels>1048576?' · '+(pixels>=3145728?'very high VRAM':'high VRAM'):'');
      list.push({group,width,height,value,label:label+' · '+width+' × '+height+suffix});
    }
    const def=capability.default_resolution;
    if(def)add('Recommended for model','Model default',def.width,def.height);
    for(const p of Array.isArray(capability.resolutions)?capability.resolutions:[])
      add('Recommended for model',p.label||'Recommended',p.width,p.height);
    for(const n of [512,768,1024])add('Square & previews',n+'px square',n,n);
    const video=[['480p',854,480],['720p',1280,720],['1080p',1920,1080],['1440p',2560,1440]];
    for(const [name,w,h] of video)add('Landscape (video formats)',name+' landscape · 16:9',w,h,true);
    for(const [name,w,h] of video)add('Portrait (video formats)',name+' portrait · 9:16',h,w,true);
    return list;
  }
  function sync(select,width,height) {
    if (!select||select.disabled)return;
    const value=valueFor(Number(width),Number(height));
    select.value=[...select.querySelectorAll('option')].some(opt=>opt.value===value)?value:'custom';
  }
  function populate(select,capability,family,width,height) {
    if(!select)return;
    select.replaceChildren();
    if(!family||!capability?.supported){
      const option=document.createElement('option');
      option.value=''; option.textContent='Select a supported model';
      select.appendChild(option);select.disabled=true;return;
    }
    let currentGroup=null,currentName='';
    for(const p of optionsFor(capability,family)){
      if(currentName!==p.group){
        currentGroup=document.createElement('optgroup');
        currentGroup.label=p.group;currentName=p.group;
        select.appendChild(currentGroup);
      }
      const option=document.createElement('option');
      option.value=p.value;option.textContent=p.label;
      currentGroup.appendChild(option);
    }
    const custom=document.createElement('option');
    custom.value='custom';custom.textContent='Custom · enter width and height';
    select.appendChild(custom);select.disabled=false;
    sync(select,width,height);
  }
  function apply(select,widthInput,heightInput){
    const match=/^(\d+)x(\d+)$/.exec(String(select?.value||''));
    if(!match)return false;
    widthInput.value=match[1];heightInput.value=match[2];return true;
  }
  function guidance(help,family,width,height){
    if(!help)return;
    if(!family){help.textContent='Choose a model to see recommended sizes. Width and height can also be entered manually.';return;}
    const w=Number(width),h=Number(height),divisor=divisorForFamily(family);
    if(!Number.isFinite(w)||!Number.isFinite(h)||w<64||h<64)
      help.textContent='Enter output dimensions of at least 64 pixels.';
    else if(w%divisor||h%divisor)
      help.textContent=family.toUpperCase()+' requires width and height in multiples of '+divisor+' pixels.';
    else if(w*h>1048576)
      help.textContent='High-resolution output uses more GPU memory. Try a short render first.';
    else help.textContent='Output size: '+w+' × '+h+'. You can edit both dimensions for custom sizes.';
  }
  window.MorphorumResolution={divisorForFamily,optionsFor,populate,sync,apply,guidance};
})();