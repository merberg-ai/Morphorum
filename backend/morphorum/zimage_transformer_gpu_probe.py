"""Z2.20c3b4 strictly gated transformer CUDA placement, no forward/generation."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact
GIB=1024**3

def probe_transformer_gpu(transformer, encoder, managed_root, *, execute=False, reserve_gib=3.0):
    result={"milestone":"z2.20c3b4","mode":"isolated_transformer_cuda_placement",
            "status":"blocked","placement_attempted":False,"forward_attempted":False,
            "generation_attempted":False,"loadable":False,"runtime_verified":False,"details":[]}
    if not execute:
        result["status"]="needs_explicit_execute"
        return result
    try:
        if not 3<=reserve_gib<=8:
            raise ValueError("Reserve must be 3 to 8 GiB.")
        check=probe_configuration(transformer,encoder,managed_root)
        if check["status"]!="config_shape_candidate_unverified":
            raise ValueError("Schema/config gate: "+"; ".join(check["reasons"]))
        if verify_fp8_stream_artifact(Path(transformer))["status"]!="verified_nonloadable":
            raise ValueError("Transformer integrity failed.")
        import psutil,torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available.")
        source=Path(transformer)/"diffusion_pytorch_model.safetensors"
        required=source.stat().st_size+int(reserve_gib*GIB)
        free,total=torch.cuda.mem_get_info(0)
        result["free_vram_before_gib"]=round(free/GIB,3)
        result["required_free_vram_gib"]=round(required/GIB,3)
        if free<required:
            raise ValueError("Insufficient actual free VRAM for whole transformer with reserve.")
        if psutil.virtual_memory().available<source.stat().st_size*2+12*GIB:
            raise ValueError("Insufficient available system RAM.")
        from diffusers import ZImageTransformer2DModel
        from accelerate import load_checkpoint_and_dispatch
        cfg=ZImageTransformer2DModel.load_config(str(Path(managed_root)/"transformer"),local_files_only=True)
        with torch.device("meta"):
            model=ZImageTransformer2DModel.from_config(cfg)
        model=load_checkpoint_and_dispatch(
            model,checkpoint=str(source),device_map={"":"cpu"},
            dtype=torch.bfloat16,strict=True).eval()
        try:
            params=list(model.parameters())
            if len(params)!=521 or any(p.is_meta or p.device.type!="cpu" for p in params):
                raise RuntimeError("CPU transformer incomplete.")
            free_now,_=torch.cuda.mem_get_info(0)
            if free_now<required:
                raise ValueError("Free VRAM declined before transfer.")
            torch.cuda.reset_peak_memory_stats(0)
            result["placement_attempted"]=True
            model.to("cuda:0")
            torch.cuda.synchronize(0)
            if any(p.is_meta or p.device.type!="cuda" for p in model.parameters()):
                raise RuntimeError("Transformer parameters not fully on CUDA.")
            result["details"].append({
                "gpu":torch.cuda.get_device_name(0),"parameter_tensors":len(params),
                "allocated_gib":round(torch.cuda.memory_allocated(0)/GIB,3),
                "peak_allocated_gib":round(torch.cuda.max_memory_allocated(0)/GIB,3),
                "free_vram_after_gib":round(torch.cuda.mem_get_info(0)[0]/GIB,3),
                "total_vram_gib":round(total/GIB,3)})
            result["status"]="transformer_cuda_placement_verified_nonloadable"
        finally:
            # Process exit releases all resources; avoid forcing another huge
            # allocation while transferring the entire model back to CPU.
            del model
    except Exception as exc:
        result["details"].append(type(exc).__name__+": "+str(exc)[:700])
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description="Z2.20c3b4 guarded transformer GPU placement")
    p.add_argument("--transformer",required=True)
    p.add_argument("--encoder",required=True)
    p.add_argument("--managed-root")
    p.add_argument("--reserve-gib",type=float,default=3.0)
    p.add_argument("--execute-transformer-gpu-placement",action="store_true")
    a=p.parse_args(argv)
    root=a.managed_root or managed_model_location("zimage")/"Z-Image-Turbo"
    r=probe_transformer_gpu(a.transformer,a.encoder,root,execute=a.execute_transformer_gpu_placement,reserve_gib=a.reserve_gib)
    print(json.dumps(r,indent=2,sort_keys=True))
    return 0 if r["status"] in ("needs_explicit_execute","transformer_cuda_placement_verified_nonloadable") else 2
if __name__=="__main__":
    raise SystemExit(main())
