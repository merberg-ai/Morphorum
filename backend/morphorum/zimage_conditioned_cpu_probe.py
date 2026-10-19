"""Z2.20c3b8: isolated CPU real-Qwen3-features -> external transformer forward.

Diagnostic interface test only, NOT validated production prompt conditioning.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from .settings import managed_model_location
from .zimage_config_probe import probe_configuration
from .zimage_fp8_stream import verify_fp8_stream_artifact

GIB = 1024**3

def probe_conditioned_cpu(transformer, encoder, managed_root, *, execute=False):
    result = {"milestone":"z2.20c3b8","mode":"isolated_cpu_real_encoder_to_transformer",
              "status":"blocked","encoder_forward_attempted":False,
              "transformer_forward_attempted":False,"generation_attempted":False,
              "cuda_used":False,"runtime_verified":False,"loadable":False,"details":[]}
    if not execute:
        result["status"]="needs_explicit_execute"
        return result
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
            raise ValueError("Start with CUDA_VISIBLE_DEVICES=-1.")
        gate=probe_configuration(transformer,encoder,managed_root)
        if gate["status"]!="config_shape_candidate_unverified":
            raise ValueError("Schema gate failed: "+"; ".join(gate["reasons"]))
        for folder in (transformer,encoder):
            if verify_fp8_stream_artifact(Path(folder))["status"]!="verified_nonloadable":
                raise ValueError("Converted artifact hash verification failed.")
        import psutil
        import torch
        if torch.cuda.is_available():
            raise RuntimeError("CUDA visible despite isolation mask.")
        encoder_file=Path(encoder)/"model.safetensors"
        transformer_file=Path(transformer)/"diffusion_pytorch_model.safetensors"
        available=psutil.virtual_memory().available
        required=encoder_file.stat().st_size+transformer_file.stat().st_size+18*GIB
        result["available_ram_gib"]=round(available/GIB,3)
        result["required_available_ram_gib"]=round(required/GIB,3)
        if available<required:
            raise ValueError("Insufficient free host RAM for both CPU models and safety reserve.")
        from transformers import Qwen3Config,Qwen3Model,Qwen2Tokenizer
        from diffusers import ZImageTransformer2DModel
        from accelerate import load_checkpoint_and_dispatch
        root=Path(managed_root)
        tok=Qwen2Tokenizer.from_pretrained(str(root/"tokenizer"),local_files_only=True)
        ids=tok("A dark castle under the moon",return_tensors="pt",add_special_tokens=False)
        n=int(ids["input_ids"].shape[1])
        if not 1<=n<=16:
            raise RuntimeError("Unsafe token count.")
        cfg_e=Qwen3Config.from_pretrained(str(root/"text_encoder"),local_files_only=True)
        enc=Qwen3Model.from_pretrained(str(Path(encoder)),config=cfg_e,
                                      local_files_only=True,torch_dtype=torch.bfloat16,
                                      low_cpu_mem_usage=True).eval()
        try:
            ep=list(enc.parameters())
            if len(ep)!=398 or any(p.is_meta or p.device.type!="cpu" for p in ep):
                raise RuntimeError("Encoder CPU weights incomplete.")
            result["encoder_forward_attempted"]=True
            with torch.inference_mode():
                embeddings=enc(input_ids=ids["input_ids"],
                               attention_mask=ids.get("attention_mask"),
                               use_cache=False,return_dict=True).last_hidden_state
            if tuple(embeddings.shape)!=(1,n,2560) or not bool(torch.isfinite(embeddings).all()):
                raise RuntimeError("Invalid encoder hidden states.")
            # The earlier transformer probe established cap_feats list of per-image [seq,2560].
            caption=[embeddings[0].contiguous()]
            cfg_t=ZImageTransformer2DModel.load_config(str(root/"transformer"),local_files_only=True)
            with torch.device("meta"):
                trans=ZImageTransformer2DModel.from_config(cfg_t)
            trans=load_checkpoint_and_dispatch(trans,checkpoint=str(transformer_file),
                                               device_map={"":"cpu"},dtype=torch.bfloat16,
                                               strict=True).eval()
            try:
                tp=list(trans.parameters())
                if len(tp)!=521 or any(p.is_meta or p.device.type!="cpu" for p in tp):
                    raise RuntimeError("Transformer CPU weights incomplete.")
                latents=[torch.zeros((16,1,4,4),dtype=torch.bfloat16)]
                timestep=torch.tensor([0.5],dtype=torch.float32)
                result["transformer_forward_attempted"]=True
                with torch.inference_mode():
                    output=trans(x=latents,t=timestep,cap_feats=caption,return_dict=False)[0][0]
                if tuple(output.shape)!=(16,1,4,4) or not bool(torch.isfinite(output).all()):
                    raise RuntimeError("Invalid transformer output shape/numerics.")
                result["details"]=[{
                    "token_count":n,"encoder_hidden_shape":list(embeddings.shape),
                    "caption_shape":list(caption[0].shape),
                    "transformer_output_shape":list(output.shape),
                    "transformer_output_dtype":str(output.dtype),
                    "finite":True,"encoder_parameter_tensors":len(ep),
                    "transformer_parameter_tensors":len(tp),
                    "process_rss_after_forward_mib":round(psutil.Process().memory_info().rss/1048576,2),
                }]
                result["status"]="real_caption_cpu_transformer_forward_verified_nonloadable"
            finally:
                del trans
        finally:
            del enc
    except Exception as exc:
        result["details"].append(type(exc).__name__+": "+str(exc)[:800])
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description="Z2.20c3b8 real caption tensor CPU integration smoke")
    p.add_argument("--transformer",required=True)
    p.add_argument("--encoder",required=True)
    p.add_argument("--managed-root")
    p.add_argument("--execute-conditioned-cpu-forward",action="store_true")
    a=p.parse_args(argv)
    root=a.managed_root or managed_model_location("zimage")/"Z-Image-Turbo"
    r=probe_conditioned_cpu(a.transformer,a.encoder,root,execute=a.execute_conditioned_cpu_forward)
    print(json.dumps(r,indent=2,sort_keys=True))
    return 0 if r["status"] in ("needs_explicit_execute","real_caption_cpu_transformer_forward_verified_nonloadable") else 2
if __name__=="__main__":
    raise SystemExit(main())
