"""Z2.20c3c2: one isolated, pipeline-style denoising step, never an image.

Native ZImagePipeline prompt encoding on CPU, then scratch transformer on CUDA.
This tests interface/math, not an approved image-generation workflow.
"""
from __future__ import annotations
import argparse, gc, json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact
GIB=1024**3

def probe_multi_step(transformer,encoder,managed_root,*,execute=False,reserve_gib=3.0,headroom_gib=1.5,steps=2):
    r={"milestone":"z2.20c3c3","mode":"isolated_native_caption_multi_scheduler_steps",
       "status":"blocked","prompt_encoding_attempted":False,
       "transformer_forward_attempted":False,"scheduler_step_attempted":False,
       "generation_attempted":False,"loadable":False,"runtime_verified":False,"details":[]}
    if not execute:
        r["status"]="needs_explicit_execute"
        return r
    try:
        if type(steps) is not int or not 2<=steps<=3:\n            raise ValueError("Steps must be 2 or 3.")\n        if not 3<=reserve_gib<=8 or not 1.5<=headroom_gib<=4:
            raise ValueError("Reserve 3..8 GiB and headroom 1.5..4 GiB required.")
        check=probe_configuration(transformer,encoder,managed_root)
        if check["status"]!="config_shape_candidate_unverified":
            raise ValueError("Config/schema gate: "+"; ".join(check["reasons"]))
        for folder in (encoder,transformer):
            if verify_fp8_stream_artifact(Path(folder))["status"]!="verified_nonloadable":
                raise ValueError("Scratch SHA-256 verification failed.")
        import psutil,torch
        ep=Path(encoder)/"model.safetensors"
        tp=Path(transformer)/"diffusion_pytorch_model.safetensors"
        available=psutil.virtual_memory().available
        required=ep.stat().st_size+tp.stat().st_size+18*GIB
        r["available_ram_gib"]=round(available/GIB,3)
        if available<required:
            raise ValueError("Host RAM below combined model files plus safety reserve.")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable.")
        free,total=torch.cuda.mem_get_info(0)
        needed=tp.stat().st_size+int(reserve_gib*GIB)
        r["free_vram_before_gib"]=round(free/GIB,3)
        r["required_free_vram_gib"]=round(needed/GIB,3)
        if free<needed:
            raise ValueError("GPU VRAM insufficient for transformer plus reserve.")
        from diffusers import ZImagePipeline,FlowMatchEulerDiscreteScheduler,ZImageTransformer2DModel
        from transformers import Qwen3Config,Qwen3Model,Qwen2Tokenizer
        from accelerate import load_checkpoint_and_dispatch
        root=Path(managed_root)
        tokenizer=Qwen2Tokenizer.from_pretrained(str(root/"tokenizer"),local_files_only=True)
        scheduler=FlowMatchEulerDiscreteScheduler.from_pretrained(str(root/"scheduler"),local_files_only=True)
        config_e=Qwen3Config.from_pretrained(str(root/"text_encoder"),local_files_only=True)
        enc=Qwen3Model.from_pretrained(str(Path(encoder)),config=config_e,local_files_only=True,
                                        torch_dtype=torch.bfloat16,low_cpu_mem_usage=True).eval()
        try:
            ep_params=list(enc.parameters())
            if len(ep_params)!=398 or any(p.is_meta or p.device.type!="cpu" for p in ep_params):
                raise RuntimeError("Encoder weights not fully bound.")
            pipe=ZImagePipeline(tokenizer=tokenizer,text_encoder=enc,transformer=None,vae=None,scheduler=scheduler)
            r["prompt_encoding_attempted"]=True
            with torch.inference_mode():
                prompt_embeddings,negative=pipe.encode_prompt(
                    prompt=["A dark castle under the moon"],device=torch.device("cpu"),
                    do_classifier_free_guidance=False,max_sequence_length=32)
            if len(prompt_embeddings)!=1 or negative:
                raise RuntimeError("Unexpected native prompt embedding container.")
            caption_cpu=prompt_embeddings[0].contiguous()
            if caption_cpu.ndim!=2 or caption_cpu.shape[1]!=2560 or not 1<=caption_cpu.shape[0]<=32:
                raise RuntimeError("Unexpected native caption feature dimensions.")
            if not bool(torch.isfinite(caption_cpu).all().item()):
                raise RuntimeError("Nonfinite native caption features.")
            del pipe
        finally:
            del enc
        gc.collect()
        # Bounded numerical integration, not image generation or full pipeline parity.
        scheduler.set_timesteps(steps,device="cpu")
        timestep=scheduler.timesteps[0]
        if not bool(torch.isfinite(timestep).item()):
            raise RuntimeError("Invalid scheduler timestep.")
        latent=torch.zeros((1,16,4,4),dtype=torch.float32,device="cpu")
        cfg_t=ZImageTransformer2DModel.load_config(str(root/"transformer"),local_files_only=True)
        with torch.device("meta"):
            trans=ZImageTransformer2DModel.from_config(cfg_t)
        trans=load_checkpoint_and_dispatch(trans,checkpoint=str(tp),device_map={"":"cpu"},
                                            dtype=torch.bfloat16,strict=True).eval()
        try:
            tpars=list(trans.parameters())
            if len(tpars)!=521 or any(p.is_meta or p.device.type!="cpu" for p in tpars):
                raise RuntimeError("Transformer CPU weight binding mismatch.")
            if torch.cuda.mem_get_info(0)[0]<needed:
                raise ValueError("GPU VRAM fell below transformer transfer threshold.")
            trans.to("cuda:0")
            torch.cuda.synchronize()
            free_loaded,_=torch.cuda.mem_get_info(0)
            r["free_vram_after_load_gib"]=round(free_loaded/GIB,3)
            if free_loaded<headroom_gib*GIB:
                raise ValueError("Post-load GPU memory below forward headroom.")
            # Z-Image forward takes a list of individual [C,F,H,W] inputs.
            cap_gpu=[caption_cpu.to("cuda:0",dtype=torch.bfloat16)]
            torch.cuda.reset_peak_memory_stats(0)
            stage_results=[]
            r["transformer_forward_attempted"]=True
            for step_index,timestep in enumerate(scheduler.timesteps):
                if not bool(torch.isfinite(timestep).item()):
                    raise RuntimeError("Nonfinite scheduler timestep.")
                sample_gpu=[latent[0].to("cuda:0",dtype=torch.bfloat16).unsqueeze(1)]
                normalized_t=(timestep.to(device="cuda:0",dtype=torch.float32)/1000.0).reshape(1)
                with torch.inference_mode():
                    predicted=trans(x=sample_gpu,t=normalized_t,cap_feats=cap_gpu,return_dict=False)[0][0]
                    torch.cuda.synchronize()
                    if predicted.device.type!="cuda" or tuple(predicted.shape)!=(16,1,4,4):
                        raise RuntimeError("Invalid prediction at step %d" % step_index)
                    if not bool(torch.isfinite(predicted).all().item()):
                        raise RuntimeError("Nonfinite prediction at step %d" % step_index)
                    noise=predicted.squeeze(1).unsqueeze(0).to(device="cpu",dtype=torch.float32)
                    del predicted,sample_gpu
                    r["scheduler_step_attempted"]=True
                    latent=scheduler.step(noise,timestep,latent,return_dict=False)[0]
                if tuple(latent.shape)!=(1,16,4,4) or not bool(torch.isfinite(latent).all().item()):
                    raise RuntimeError("Invalid latent at step %d" % step_index)
                stage_results.append({
                    "step_index":step_index,
                    "scheduler_timestep":float(timestep.item()),
                    "transformer_timestep_input":float(normalized_t.item()),
                    "latent_finite":True,
                    "free_vram_gib":round(torch.cuda.mem_get_info(0)[0]/GIB,3)
                })
            r["details"]=[{
                "steps_completed":len(stage_results),
                "step_results":stage_results,
                "native_caption_shape":list(caption_cpu.shape),
                "updated_latent_shape":list(latent.shape),
                "finite":True,
                "transformer_parameter_tensors":len(tpars),
                "peak_gpu_allocated_gib":round(torch.cuda.max_memory_allocated(0)/GIB,3),
                "free_vram_after_forward_gib":round(torch.cuda.mem_get_info(0)[0]/GIB,3),
                "total_vram_gib":round(total/GIB,3),
            }]
            r["status"]="native_caption_multi_scheduler_steps_verified_nonloadable"
        finally:
            del trans
    except Exception as exc:
        r["details"].append(type(exc).__name__+": "+str(exc)[:850])
    return r

def main(argv=None):
    p=argparse.ArgumentParser(description="Z2.20c3c3 bounded native-caption scheduler steps")
    p.add_argument("--transformer",required=True)
    p.add_argument("--encoder",required=True)
    p.add_argument("--managed-root")
    p.add_argument("--execute-multi-step",action="store_true")
    p.add_argument("--steps",type=int,default=2)
    p.add_argument("--reserve-gib",type=float,default=3)
    p.add_argument("--headroom-gib",type=float,default=1.5)
    a=p.parse_args(argv)
    root=a.managed_root or managed_model_location("zimage")/"Z-Image-Turbo"
    r=probe_multi_step(a.transformer,a.encoder,root,execute=a.execute_multi_step,
                     reserve_gib=a.reserve_gib,headroom_gib=a.headroom_gib,steps=a.steps)
    print(json.dumps(r,sort_keys=True,indent=2))
    return 0 if r["status"] in ("needs_explicit_execute","native_caption_multi_scheduler_steps_verified_nonloadable") else 2

if __name__=="__main__":
    raise SystemExit(main())
