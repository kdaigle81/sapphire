"""ComfyUI image generation — submit prompts to a local ComfyUI server."""

import base64
import io
import json
import logging
import random
import time

logger = logging.getLogger(__name__)

ENABLED = True
EMOJI = "\U0001F3A8"

# Qwen Image 2512 aspect ratio presets (from the workflow)
ASPECT_SIZES = {
    "1:1":  (1328, 1328),
    "16:9": (1664, 928),
    "9:16": (928, 1664),
    "4:3":  (1472, 1104),
    "3:4":  (1104, 1472),
    "3:2":  (1584, 1056),
    "2:3":  (1056, 1584),
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "comfy_generate",
            "description": (
                "Generate an image using ComfyUI with the Qwen Image 2512 model. "
                "Describe what you want to see in detail. The image appears in chat for both you and the user. "
                "Supports various aspect ratios. Be descriptive — this model responds well to detailed prompts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed image description. Be specific about subject, style, lighting, composition."
                    },
                    "aspect_ratio": {
                        "type": "string",
                        "enum": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
                        "description": "Image aspect ratio (default: 1:1)"
                    },
                    "seed": {
                        "type": "integer",
                        "description": "Seed for reproducibility. Omit for random."
                    }
                },
                "required": ["prompt"]
            }
        }
    }
]


def _get_settings():
    try:
        from core.plugin_loader import plugin_loader
        return plugin_loader.get_plugin_settings("gallery") or {}
    except Exception:
        return {}


def _build_workflow(prompt_text, width, height, seed):
    """Build a ComfyUI API-format workflow for Qwen Image 2512.

    This is a minimal workflow that loads the models and generates an image.
    """
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["37", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": 30,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text,
                "clip": ["38", 0]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "",
                "clip": ["38", 0]
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["39", 0]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "Sapphire"
            }
        },
        "37": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "qwen_image_2512_fp8_e4m3fn.safetensors",
                "weight_dtype": "fp8_e4m3fn"
            }
        },
        "38": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "type": "qwen_image",
                "device": "default"
            }
        },
        "39": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "qwen_image_vae.safetensors"
            }
        },
    }


def execute(function_name, arguments, config=None, plugin_settings=None, credentials=None):
    if function_name != "comfy_generate":
        return f"Unknown function: {function_name}", False

    import requests

    prompt_text = arguments.get("prompt", "").strip()
    if not prompt_text:
        return "No prompt provided", False

    aspect = arguments.get("aspect_ratio", "1:1")
    width, height = ASPECT_SIZES.get(aspect, (1328, 1328))
    seed = arguments.get("seed") or random.randint(1, 2**31)

    settings = plugin_settings or _get_settings()
    comfy_url = settings.get("comfy_url", "http://127.0.0.1:8188")

    # Build and submit workflow
    workflow = _build_workflow(prompt_text, width, height, seed)

    logger.info(f"[COMFY] Generating: {prompt_text[:60]}... ({width}x{height}, seed={seed})")

    try:
        # Check if ComfyUI is running
        try:
            requests.get(f"{comfy_url}/system_stats", timeout=3)
        except Exception:
            return f"ComfyUI not reachable at {comfy_url}. Make sure it's running.", False

        # Submit prompt
        resp = requests.post(
            f"{comfy_url}/prompt",
            json={"prompt": workflow},
            timeout=10,
        )
        if resp.status_code != 200:
            return f"ComfyUI rejected the workflow: {resp.text[:200]}", False

        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            return "ComfyUI returned no prompt_id", False

        logger.info(f"[COMFY] Queued prompt {prompt_id}")

        # Poll for completion
        max_wait = 300  # 5 minutes
        poll_interval = 2
        elapsed = 0
        output_images = None

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            hist_resp = requests.get(f"{comfy_url}/history/{prompt_id}", timeout=10)
            if hist_resp.status_code != 200:
                continue

            history = hist_resp.json()
            if prompt_id not in history:
                continue

            entry = history[prompt_id]
            status = entry.get("status", {})

            if status.get("status_str") == "error":
                msgs = status.get("messages", [])
                error_text = str(msgs) if msgs else "Unknown error"
                return f"ComfyUI generation failed: {error_text}", False

            if status.get("completed", False) or entry.get("outputs"):
                output_images = entry.get("outputs", {})
                break

        if output_images is None:
            return f"ComfyUI timed out after {max_wait}s", False

        # Find the SaveImage output
        image_data = None
        for node_id, node_output in output_images.items():
            images = node_output.get("images", [])
            if images:
                img_info = images[0]  # Take first image
                filename = img_info.get("filename")
                subfolder = img_info.get("subfolder", "")
                img_type = img_info.get("type", "output")

                # Download the image
                params = {"filename": filename, "type": img_type}
                if subfolder:
                    params["subfolder"] = subfolder
                img_resp = requests.get(f"{comfy_url}/view", params=params, timeout=30)
                if img_resp.status_code == 200:
                    image_data = img_resp.content
                    break

        if not image_data:
            return "Generation completed but no image found in output", False

        # Resize for chat display if huge
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_data))
            max_px = 2160
            if max(img.size) > max_px:
                ratio = max_px / max(img.size)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            image_data = buf.getvalue()
        except Exception:
            pass  # Send original if resize fails

        b64 = base64.b64encode(image_data).decode()

        summary = (
            f"Generated image: {aspect} ({width}x{height}), seed={seed}\n"
            f"Prompt: {prompt_text[:200]}"
        )

        return {
            "text": summary,
            "images": [{"data": b64, "media_type": "image/jpeg"}]
        }, True

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to ComfyUI at {comfy_url}. Is it running?", False
    except Exception as e:
        logger.error(f"[COMFY] Generation failed: {e}", exc_info=True)
        return f"ComfyUI generation error: {e}", False
