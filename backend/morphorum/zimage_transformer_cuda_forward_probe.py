"""Z2.20c3b7: tiny standalone BF16 transformer CUDA forward, opt-in only."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact
GIB=1024**3

def probe_transformer_cuda_forward(transformer, encoder, managed_root, *, execute=False, reserve_gib=3.0, forward_headroom_gib=1.5):
    r={"milestone":"z2.20c3b7","mode":"isolated_tiny_transformer_cuda_forward",
       "status":"blocked","forward_attempted":False,"generation_attempted":False,
       "loadable":False,"runtime_verified":False,"details":[]}
    if not execute:
        r["status"]="needs_explicit_execute"
        return r
    try:
        if not 3 <= reserve_gib <= 8 or not 1.5 <= forward_headroom_gib <= 4:
            raise ValueError("Reserve must be 3..8 GiB; forward headroom 1.5..4 GiB.")
        cfg_gate=probe_configuration(transformer,encoder,managed_root)
        if cfg_gate["status"]!="config_shape_candidate_unverified":
            raise ValueError("Config gate failed: "+"; ".join(cfg_gate["reasons"]))
        if verify_fp8_stream_artifact(Path(transformer))["status"]!="verified_nonloadable":
            raise ValueError("Transformer scratch integrity failed.")
        import torch,psutil
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable.")
        path=Path(transformer)/"diffusion_pytorch_model.safetensors"
        needed=path.stat().st_size+int(reserve_gib*GIB)
        free,total=torch.cuda.mem_get_info(0)
        r["free_vram_before_gib"]=round(free/GIB,3)
        r["required_free_vram_gib"]=round(needed/GIB,3)
        if free<needed:
            raise ValueError("Measured free VRAM below full transformer weight + reserve.")
        if psutil.virtual_memory().available < path.stat().st_size*2+12*GIB:
            raise ValueError("Insufficient available system RAM.")
        from diffusers import ZImageTransformer2DModel
        from accelerate import load_checkpoint_and_dispatch
        cfg=ZImageTransformer2DModel.load_config(str(Path(managed_root)/"transformer"),local_files_only=True)
        if int(cfg.get("in_channels",-1))!=16 or int(cfg.get("cap_feat_dim",-1))!=2560:
            raise ValueError("Unexpected transformer channel or caption dimensions.")
        with torch.device("meta"):
            model=ZImageTransformer2DModel.from_config(cfg)
        model=load_checkpoint_and_dispatch(model,checkpoint=str(path),device_map={"":"cpu"},
                                           dtype=torch.bfloat16,strict=True).eval()
        try:
            pars=list(model.parameters())
            if len(pars)!=521 or any(p.is_meta or p.device.type!="cpu" for p in pars):
                raise RuntimeError("Incomplete CPU transformer.")
            if torch.cuda.mem_get_info(0)[0]<needed:
                raise ValueError("GPU free memory fell below loading threshold.")
            model.to("cuda:0")
            torch.cuda.synchronize()
            if any(p.is_meta or p.device.type!="cuda" for p in pars):
                raise RuntimeError("Incomplete CUDA transformer.")
            free_loaded,_=torch.cuda.mem_get_info(0)
            r["free_vram_after_load_gib"]=round(free_loaded/GIB,3)
            r["required_forward_headroom_gib"]=forward_headroom_gib
            if free_loaded < forward_headroom_gib*GIB:
                raise ValueError("Transformer loaded but insufficient free VRAM for forward headroom.")
            torch.cuda.reset_peak_memory_stats(0)
            x=[torch.zeros((16,1,4,4),dtype=torch.bfloat16,device="cuda:0")]
            cap=[torch.zeros((1,2560),dtype=torch.bfloat16,device="cuda:0")]
            t=torch.tensor([0.5],dtype=torch.float32,device="cuda:0")
            r["forward_attempted"]=True
            with torch.inference_mode():
                output=model(x=x,t=t,cap_feats=cap,return_dict=False)
                value=output[0][0]
                torch.cuda.synchronize()
                if value.device.type!="cuda" or tuple(value.shape)!=(16,1,4,4):
                    raise RuntimeError("Unexpected transformer output shape/device.")
                if not bool(torch.isfinite(value).all().item()):
                    raise RuntimeError("Nonfinite transformer output.")
                r["details"]=[{
                    "input_shape":[16,1,4,4],"caption_shape":[1,2560],
                    "output_shape":list(value.shape),"output_dtype":str(value.dtype),
                    "finite":True,"parameter_tensors":len(pars),
                    "allocated_gib":round(torch.cuda.memory_allocated(0)/GIB,3),
                    "peak_allocated_gib":round(torch.cuda.max_memory_allocated(0)/GIB,3),
                    "free_vram_after_forward_gib":round(torch.cuda.mem_get_info(0)[0]/GIB,3),
                    "total_vram_gib":round(total/GIB,3)}]
            r["status"]="transformer_cuda_forward_verified_nonloadable"
        finally:
            del model
    except Exception as exc:
        r["details"].append(type(exc).__name__+": "+str(exc)[:800])
    return r

def main(argv=None):
    p=argparse.ArgumentParser(description="Z2.20c3b7 tiny transformer CUDA forward")
    p.add_argument("--transformer",required=True)
    p.add_argument("--encoder",required=True)
    p.add_argument("--managed-root")
    p.add_argument("--execute-transformer-gpu-forward",action="store_true")
    p.add_argument("--reserve-gib",type=float,default=3)
    p.add_argument("--forward-headroom-gib",type=float,default=1.5)
    a=p.parse_args(argv)
    root=a.managed_root or managed_model_location("zimage")/"Z-Image-Turbo"
    r=probe_transformer_cuda_forward(a.transformer,a.encoder,root,execute=a.execute_transformer_gpu_forward,
                                    reserve_gib=a.reserve_gib,forward_headroom_gib=a.forward_headroom_gib)
    print(json.dumps(r,indent=2,sort_keys=True))
    return 0 if r["status"] in ("needs_explicit_execute","transformer_cuda_forward_verified_nonloadable") else 2

if __name__=="__main__":
    raise SystemExit(main())
