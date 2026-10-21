/* PS1.1: Pure Prompt Studio <-> native Editor prompt contracts. */
(function (root) {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  const modeOK = mode => mode === 'hold' || mode === 'blend';
  const fail = (code,message) => ({ok:false,code,message});
  function legacyTrack(map, mode) {
    const frames=Object.keys(map||{}).map(Number).filter(Number.isInteger).sort((a,b)=>a-b);
    if (!frames.includes(0)) frames.unshift(0);
    return {kind:'prompt',interpolation:modeOK(mode)?mode:'blend',
      keyframes:frames.map(frame=>({frame,value:String((map||{})[String(frame)]||'')}))};
  }
  function nativeTracks(project) {
    const existing=project?.tracks?.prompts || {},mode=project?.animation?.prompt_transition;
    return {
      positive:copy(existing.positive||legacyTrack(project?.prompts,mode)),
      negative:copy(existing.negative||legacyTrack(project?.negative_prompts,mode))
    };
  }
  function validateTracks(tracks,maxFrames) {
    if (!Number.isInteger(maxFrames)||maxFrames<1||maxFrames>1000000)
      return fail('INVALID_LENGTH','Project frame count is invalid.');
    if (!tracks||typeof tracks!=='object'||Array.isArray(tracks))
      return fail('INVALID_TRACKS','Positive and negative prompt tracks are required.');
    const out={};let total=0;
    for (const name of ['positive','negative']) {
      const t=tracks[name];
      if (!t||t.kind!=='prompt'||!modeOK(t.interpolation)||
          !Array.isArray(t.keyframes)||t.keyframes.length<1||t.keyframes.length>3000)
        return fail('INVALID_TRACK','Invalid '+name+' prompt lane.');
      let previous=-1;const points=[];
      for (const k of t.keyframes) {
        if (!k||!Number.isInteger(k.frame)||k.frame<=previous||
            k.frame>=maxFrames||typeof k.value!=='string'||k.value.length>32768)
          return fail('INVALID_KEYFRAME','Invalid '+name+' keyframe, frame order or prompt length.');
        previous=k.frame;total+=k.value.length;
        if (total>4000000) return fail('INVALID_SIZE','Prompt draft exceeds maximum length.');
        points.push({frame:k.frame,value:k.value});
      }
      if (points[0].frame!==0) return fail('MISSING_FRAME_ZERO','Each lane must start at frame zero.');
      out[name]={kind:'prompt',interpolation:t.interpolation,keyframes:points};
    }
    return {ok:true,tracks:out};
  }
  function mapsFromTracks(tracks) {
    const maps={};
    for (const [lane,field] of [['positive','prompts'],['negative','negative_prompts']]) {
      maps[field]={};
      for (const p of tracks[lane].keyframes) maps[field][String(p.frame)]=p.value;
    }
    return maps;
  }
  function snapshotTracks(project,baselineRows,currentRows,positiveMode) {
    if (!project||!Array.isArray(baselineRows)||!Array.isArray(currentRows))
      return fail('NO_EDITOR','Editor prompt form is unavailable.');
    if (baselineRows.length!==currentRows.length||
        baselineRows.some((v,i)=>!v||!currentRows[i]||v.frame!==currentRows[i].frame))
      return fail('STRUCTURAL_EDIT','Editor prompt rows have been moved, added or removed. Review/save row edits before importing to Studio.');
    const tracks=nativeTracks(project),maxFrames=Number(project?.animation?.max_frames);
    for (const name of ['positive','negative']) {
      const points=new Map(tracks[name].keyframes.map(p=>[p.frame,p.value]));
      for (let i=0;i<currentRows.length;i++) {
        const old=baselineRows[i],now=currentRows[i];
        if (typeof old[name]!=='string'||typeof now[name]!=='string')
          return fail('INVALID_ROW','Editor prompt text must be a string.');
        if (old[name]!==now[name]) points.set(now.frame,now[name]);
      }
      tracks[name].keyframes=[...points.entries()].sort((a,b)=>a[0]-b[0])
        .map(([frame,value])=>({frame,value}));
    }
    if (positiveMode!==undefined) tracks.positive.interpolation=positiveMode;
    const checked=validateTracks(tracks,maxFrames);
    return checked.ok?{ok:true,tracks:checked.tracks,maps:mapsFromTracks(checked.tracks)}:checked;
  }
  function buildPromptOnlyPatch(project,proposed) {
    if (!project?.tracks||!project?.animation)
      return fail('INVALID_PROJECT','Native project timeline is unavailable.');
    const check=validateTracks(proposed,Number(project.animation.max_frames));
    if (!check.ok) return check;
    const result=copy(project);
    result.tracks.prompts={...(result.tracks.prompts||{}),
      positive:{...(result.tracks.prompts?.positive||{}),...check.tracks.positive},
      negative:{...(result.tracks.prompts?.negative||{}),...check.tracks.negative}};
    Object.assign(result,mapsFromTracks(check.tracks));
    result.animation.prompt_transition=check.tracks.positive.interpolation;
    return {ok:true,project:result,tracks:check.tracks};
  }
  function diffTracks(before,after) {
    const counts={positive:0,negative:0,modes:0};
    for (const name of ['positive','negative']) {
      const a=before[name],b=after[name];
      if (a.interpolation!==b.interpolation) counts.modes++;
      const old=new Map(a.keyframes.map(p=>[p.frame,p.value]));
      const now=new Map(b.keyframes.map(p=>[p.frame,p.value]));
      for (const frame of new Set([...old.keys(),...now.keys()]))
        if (!old.has(frame)||!now.has(frame)||old.get(frame)!==now.get(frame)) counts[name]++;
    }
    return {...counts,total:counts.positive+counts.negative+counts.modes};
  }
  const api={nativeTracks,validateTracks,mapsFromTracks,snapshotTracks,buildPromptOnlyPatch,diffTracks};
  if (typeof module==='object'&&module.exports) module.exports=api;
  if (root) root.MorphorumPromptStudioBridge=api;
})(typeof window==='object'?window:null);
