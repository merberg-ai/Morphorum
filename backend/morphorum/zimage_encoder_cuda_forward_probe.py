"""Z2.20c3b6: isolated real Qwen3 CUDA forward. No image generation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024**3

def probe_encoder_cuda_forward(transformer, encoder, managed_root, *, execute=False, reserve_gib=3.0):
    result = {"milestone":"z2.20c3b6", "mode":"isolated_encoder_cuda_forward",
              "status":"blocked","forward_attempted":False,"generation_attempted":False,
              "loadable":False,"runtime_verified":False,"details":[]}
    if not execute:
        result["status"]="needs_explicit_execute"
        return result
    try:
        if not 3.0 <= reserve_gib <= 8.0:
            raise ValueError("Reserve must be 3..8 GiB.")
        gate=probe_configuration(transformer,encoder,managed_root)
        if gate["status"]!="config_shape_candidate_unverified":
            raise ValueError("Schema gate failed: "+"; ".join(gate["reasons"]))
        if verify_fp8_stream_artifact(Path(encoder))["status"]!="verified_nonloadable":
            raise ValueError("Encoder scratch integrity failed.")
        import torch, psutil
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable.")
        path=Path(encoder)/"model.safetensors"
        required_vram=path.stat().st_size+int(reserve_gib*GIB)
        free,total=torch.cuda.mem_get_info(0)
        result["free_vram_before_gib"]=round(free/GIB,3)
        result["required_free_vram_gib"]=round(required_vram/GIB,3)
        if free < required_vram:
            raise ValueError("Insufficient actual free VRAM for encoder + reserve.")
        if psutil.virtual_memory().available < 2*path.stat().st_size+12*GIB:
            raise ValueError("Insufficient system RAM.")
        from transformers import Qwen3Config,Qwen3Model,Qwen2Tokenizer
        root=Path(managed_root)
        cfg=Qwen3Config.from_pretrained(str(root/"text_encoder"),local_files_only=True)
        tokenizer=Qwen2Tokenizer.from_pretrained(str(root/"tokenizer"),local_files_only=True)
        tokens=tokenizer("A dark castle under the moon",return_tensors="pt",add_special_tokens=False)
        ids=tokens["input_ids"]
        if not 1 <= ids.shape[1] <= 16:
            raise ValueError("Token count outside guarded range.")
        model=Qwen3Model.from_pretrained(str(Path(encoder)),config=cfg,local_files_only=True,
                                           torch_dtype=torch.bfloat16,low_cpu_mem_usage=True).eval()
        try:
            params=list(model.parameters())
            if len(params)!=398 or any(p.is_meta or p.device.type!="cpu" for p in params):
                raise RuntimeError("Incomplete CPU encoder.")
            if torch.cuda.mem_get_info(0)[0] < required_vram:
                raise ValueError("Free VRAM declined before transfer.")
            model.to("cuda:0")
            torch.cuda.synchronize()
            if any(p.device.type!="cuda" for p in params):
                raise RuntimeError("GPU encoder incomplete.")
            free_loaded,_=torch.cuda.mem_get_info(0)
            result["free_vram_after_load_gib"]=round(free_loaded/GIB,3)
            # Keep additional 1 GiB free for small-token forward buffers.
            if free_loaded < GIB:
                raise ValueError("Insufficient headroom for CUDA encoder forward.")
            torch.cuda.reset_peak_memory_stats(0)
            result["forward_attempted"]=True
            with torch.inference_mode():
                output=model(input_ids=ids.to("cuda:0"),
                             attention_mask=tokens.get("attention_mask").to("cuda:0") if tokens.get("attention_mask") is not None else None,
                             use_cache=False,return_dict=True)
                hidden=output.last_hidden_state
                torch.cuda.synchronize()
                if hidden.device.type!="cuda" or hidden.ndim!=3 or hidden.shape[0]!=1 or hidden.shape[1]!=ids.shape[1]:
                    raise RuntimeError("Unexpected hidden state shape/device.")
                if not bool(torch.isfinite(hidden).all().item()):
                    raise RuntimeError("Nonfinite encoder output.")
                result["details"]=[{
                    "tokens":int(ids.shape[1]),"hidden_shape":list(hidden.shape),
                    "output_dtype":str(hidden.dtype),"finite":True,
                    "parameter_tensors":len(params),
                    "memory_allocated_gib":round(torch.cuda.memory_allocated(0)/GIB,3),
                    "peak_allocated_gib":round(torch.cuda.max_memory_allocated(0)/GIB,3),
                    "free_vram_after_forward_gib":round(torch.cuda.mem_get_info(0)[0]/GIB,3),
                    "total_vram_gib":round(total/GIB,3)}]
            result["status"]="encoder_cuda_forward_verified_nonloadable"
        finally:
            del model
    except Exception as exc:
        result["details"].append(type(exc).__name__+": "+str(exc)[:700])
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description="Z2.20c3b6 standalone Qwen3 CUDA forward")
    p.add_argument("--transformer",required=True)
    p.add_argument("--encoder",required=True)
    p.add_argument("--managed-root")
    p.add_argument("--reserve-gib",type=float,default=3.0)
    p.add_argument("--execute-encoder-gpu-forward",action="store_true")
    a=p.parse_args(argv)
    root=a.managed_root or managed_model_location("zimage")/"Z-Image-Turbo"
    r=probe_encoder_cuda_forward(a.transformer,a.encoder,root,
                                 execute=a.execute_encoder_gpu_forward,reserve_gib=a.reserve_gib)
    print(json.dumps(r,indent=2,sort_keys=True))
    return 0 if r["status"] in ("needs_explicit_execute","encoder_cuda_forward_verified_nonloadable") else 2

if __name__=="__main__":
    raise SystemExit(main())
