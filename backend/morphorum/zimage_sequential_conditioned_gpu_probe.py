"""Z2.20c3b9 isolated real-caption sequential CUDA forwards, no image generation."""
from __future__ import annotations
import argparse, gc, json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact
GIB=1024**3

def probe_sequential_conditioned_gpu(transformer,encoder,managed_root,*,execute=False,reserve_gib=3.0,headroom_gib=1.5):
    r={"milestone":"z2.20c3b9","mode":"sequential_real_caption_cuda_forwards",
       "status":"blocked","encoder_forward_attempted":False,
       "encoder_evicted":False,"transformer_forward_attempted":False,
       "generation_attempted":False,"runtime_verified":False,"loadable":False,"details":[]}
    if not execute:
        r["status"]="needs_explicit_execute"
        return r
    try:
        if not 3<=reserve_gib<=8 or not 1.5<=headroom_gib<=4:
            raise ValueError("Reserve 3..8 GiB, forward headroom 1.5..4 GiB required.")
        check=probe_configuration(transformer,encoder,managed_root)
        if check["status"]!="config_shape_candidate_unverified":
            raise ValueError("Schema gate failed: "+"; ".join(check["reasons"]))
        for folder in (encoder,transformer):
            if verify_fp8_stream_artifact(Path(folder))["status"]!="verified_nonloadable":
                raise ValueError("Scratch hash gate failed.")
        import torch,psutil
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available.")
        ep=Path(encoder)/"model.safetensors"
        tp=Path(transformer)/"diffusion_pytorch_model.safetensors"
        required_ram=ep.stat().st_size+tp.stat().st_size+18*GIB
        r["available_ram_gib"]=round(psutil.virtual_memory().available/GIB,3)
        if psutil.virtual_memory().available<required_ram:
            raise ValueError("Insufficient host RAM for combined CPU weights.")
        required_vram=max(ep.stat().st_size,tp.stat().st_size)+int(reserve_gib*GIB)
        before,total=torch.cuda.mem_get_info(0)
        r["free_vram_before_gib"]=round(before/GIB,3)
        r["required_free_vram_gib"]=round(required_vram/GIB,3)
        if before<required_vram:
            raise ValueError("Insufficient real free VRAM for the larger model.")
        from transformers import Qwen3Model,Qwen3Config,Qwen2Tokenizer
        from diffusers import ZImageTransformer2DModel
        from accelerate import load_checkpoint_and_dispatch
        root=Path(managed_root)
        tokenizer=Qwen2Tokenizer.from_pretrained(str(root/"tokenizer"),local_files_only=True)
        batch=tokenizer("A dark castle under the moon",return_tensors="pt",add_special_tokens=False)
        n=int(batch["input_ids"].shape[1])
        if not 1<=n<=16:
            raise ValueError("Unexpected token count.")
        config=Qwen3Config.from_pretrained(str(root/"text_encoder"),local_files_only=True)
        enc=Qwen3Model.from_pretrained(str(Path(encoder)),config=config,local_files_only=True,
                                        torch_dtype=torch.bfloat16,low_cpu_mem_usage=True).eval()
        try:
            eparams=list(enc.parameters())
            if len(eparams)!=398 or any(p.is_meta or p.device.type!="cpu" for p in eparams):
                raise RuntimeError("Incomplete CPU encoder.")
            if torch.cuda.mem_get_info(0)[0]<ep.stat().st_size+reserve_gib*GIB:
                raise ValueError("Insufficient VRAM before encoder transfer.")
            enc.to("cuda:0")
            torch.cuda.synchronize()
            if any(p.device.type!="cuda" for p in eparams):
                raise RuntimeError("Encoder not fully on CUDA.")
            if torch.cuda.mem_get_info(0)[0]<headroom_gib*GIB:
                raise ValueError("Insufficient post-load encoder headroom.")
            r["encoder_forward_attempted"]=True
            with torch.inference_mode():
                features=enc(input_ids=batch["input_ids"].to("cuda:0"),
                             attention_mask=batch.get("attention_mask").to("cuda:0") if batch.get("attention_mask") is not None else None,
                             use_cache=False,return_dict=True).last_hidden_state
                torch.cuda.synchronize()
                if tuple(features.shape)!=(1,n,2560) or not bool(torch.isfinite(features).all().item()):
                    raise RuntimeError("Invalid encoder features.")
                caption_cpu=features[0].to("cpu").contiguous()
            del features
            r["details"].append({"stage":"encoder_cuda_forward",
                                 "caption_shape":list(caption_cpu.shape),
                                 "free_vram_gib":round(torch.cuda.mem_get_info(0)[0]/GIB,3)})
            enc.to("cpu")
            torch.cuda.synchronize()
            gc.collect()
            torch.cuda.empty_cache()
            if any(p.device.type!="cpu" for p in eparams):
                raise RuntimeError("Encoder did not return to CPU.")
            free,_=torch.cuda.mem_get_info(0)
            r["details"].append({"stage":"encoder_evicted",
                                 "allocator_gib":round(torch.cuda.memory_allocated(0)/GIB,3),
                                 "free_vram_gib":round(free/GIB,3)})
            if free<tp.stat().st_size+reserve_gib*GIB:
                raise ValueError("Insufficient GPU memory after encoder eviction.")
            r["encoder_evicted"]=True
            cfg=ZImageTransformer2DModel.load_config(str(root/"transformer"),local_files_only=True)
            with torch.device("meta"):
                trans=ZImageTransformer2DModel.from_config(cfg)
            trans=load_checkpoint_and_dispatch(trans,checkpoint=str(tp),device_map={"":"cpu"},dtype=torch.bfloat16,strict=True).eval()
            try:
                tparams=list(trans.parameters())
                if len(tparams)!=521 or any(p.is_meta or p.device.type!="cpu" for p in tparams):
                    raise RuntimeError("Incomplete CPU transformer.")
                if torch.cuda.mem_get_info(0)[0]<tp.stat().st_size+reserve_gib*GIB:
                    raise ValueError("VRAM fell below transformer placement gate.")
                trans.to("cuda:0")
                torch.cuda.synchronize()
                if any(p.device.type!="cuda" for p in tparams):
                    raise RuntimeError("Transformer incomplete on CUDA.")
                free_loaded,_=torch.cuda.mem_get_info(0)
                if free_loaded<headroom_gib*GIB:
                    raise ValueError("Insufficient transformer forward headroom.")
                torch.cuda.reset_peak_memory_stats(0)
                caption=[caption_cpu.to("cuda:0")]
                latents=[torch.zeros((16,1,4,4),device="cuda:0",dtype=torch.bfloat16)]
                ts=torch.tensor([0.5],device="cuda:0",dtype=torch.float32)
                r["transformer_forward_attempted"]=True
                with torch.inference_mode():
                    output=trans(x=latents,t=ts,cap_feats=caption,return_dict=False)[0][0]
                    torch.cuda.synchronize()
                    if tuple(output.shape)!=(16,1,4,4) or not bool(torch.isfinite(output).all().item()):
                        raise RuntimeError("Invalid transformer output.")
                r["details"].append({"stage":"conditioned_transformer_cuda_forward",
                                     "output_shape":list(output.shape),"finite":True,
                                     "dtype":str(output.dtype),
                                     "allocated_gib":round(torch.cuda.memory_allocated(0)/GIB,3),
                                     "peak_allocated_gib":round(torch.cuda.max_memory_allocated(0)/GIB,3),
                                     "free_vram_gib":round(torch.cuda.mem_get_info(0)[0]/GIB,3),
                                     "total_vram_gib":round(total/GIB,3)})
                r["status"]="sequential_real_caption_cuda_forwards_verified_nonloadable"
            finally:
                del trans
        finally:
            del enc
    except Exception as exc:
        r["details"].append(type(exc).__name__+": "+str(exc)[:750])
    return r

def main(argv=None):
    p=argparse.ArgumentParser(description="Z2.20c3b9 guarded real-caption sequential CUDA forwards")
    p.add_argument("--transformer",required=True)
    p.add_argument("--encoder",required=True)
    p.add_argument("--managed-root")
    p.add_argument("--reserve-gib",type=float,default=3)
    p.add_argument("--headroom-gib",type=float,default=1.5)
    p.add_argument("--execute-sequential-conditioned-gpu",action="store_true")
    a=p.parse_args(argv)
    root=a.managed_root or managed_model_location("zimage")/"Z-Image-Turbo"
    r=probe_sequential_conditioned_gpu(a.transformer,a.encoder,root,execute=a.execute_sequential_conditioned_gpu,
                                        reserve_gib=a.reserve_gib,headroom_gib=a.headroom_gib)
    print(json.dumps(r,indent=2,sort_keys=True))
    return 0 if r["status"] in ("needs_explicit_execute","sequential_real_caption_cuda_forwards_verified_nonloadable") else 2
if __name__=="__main__":
    raise SystemExit(main())
