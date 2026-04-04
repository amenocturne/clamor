#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Generate images using OpenRouter API with Gemini Flash Image.

Usage:
    imagine.py <prompt> [options]

Arguments:
    prompt          Text description of the image to generate

Options:
    --model=MODEL   Model to use (default: google/gemini-3.1-flash-image-preview)
    --ref=PATH      Reference image for editing/variation
    --output=PATH   Output file path (default: tmp/imagine_<timestamp>.png)
    --size=WxH      Desired image dimensions hint (e.g., 1024x1024)

Environment:
    OPENROUTER_API_KEY  Required.

Examples:
    imagine.py "a cat wearing a top hat, watercolor style"
    imagine.py "make the background sunset" --ref=photo.jpg
    imagine.py "pixel art castle" --output=/abs/path/castle.png
"""

import base64
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

import httpx


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"


def find_tmp_dir(start: Path) -> Path:
    """Find tmp directory by walking up to project root."""
    current = start.resolve()
    while current != current.parent:
        if (current / "CLAUDE.md").exists():
            return current / "tmp"
        current = current.parent
    return Path.cwd() / "tmp"


def parse_args(args: list[str]) -> dict:
    """Parse command line arguments."""
    result = {
        "prompt": None,
        "model": DEFAULT_MODEL,
        "ref": None,
        "output": None,
        "size": None,
    }

    prompt_parts = []
    for arg in args:
        if arg.startswith("--model="):
            result["model"] = arg.split("=", 1)[1]
        elif arg.startswith("--ref="):
            result["ref"] = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            result["output"] = arg.split("=", 1)[1]
        elif arg.startswith("--size="):
            result["size"] = arg.split("=", 1)[1]
        elif not arg.startswith("-"):
            prompt_parts.append(arg)

    if prompt_parts:
        result["prompt"] = " ".join(prompt_parts)

    return result


def encode_image(path: Path) -> tuple[str, str]:
    """Read and base64-encode an image file. Returns (b64_data, mime_type)."""
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        ext_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime_type = ext_map.get(path.suffix.lower(), "image/png")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return data, mime_type


def build_messages(prompt: str, ref_path: Path | None, size: str | None) -> list[dict]:
    """Build the chat messages payload."""
    text = prompt
    if size:
        text += f"\n\nDesired image dimensions: {size}."

    content: list[dict] = []

    if ref_path:
        b64_data, mime_type = encode_image(ref_path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
        })

    content.append({"type": "text", "text": text})

    return [{"role": "user", "content": content}]


def extract_images(response_data: dict) -> list[tuple[bytes, str]]:
    """Extract image bytes from API response. Returns list of (bytes, extension)."""
    images = []

    if "choices" not in response_data or not response_data["choices"]:
        return images

    message = response_data["choices"][0].get("message", {})

    # Primary: OpenRouter returns images in message.images array
    for img in message.get("images", []):
        if isinstance(img, dict) and img.get("type") == "image_url":
            url = img.get("image_url", {}).get("url", "")
            img_bytes, ext = decode_data_url(url)
            if img_bytes:
                images.append((img_bytes, ext))

    if images:
        return images

    # Fallback: check content array for image_url parts
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                img_bytes, ext = decode_data_url(url)
                if img_bytes:
                    images.append((img_bytes, ext))

    # Fallback: content string with embedded base64 data URLs
    if not images and isinstance(content, str):
        pattern = r'data:(image/\w+);base64,([A-Za-z0-9+/=]+)'
        for match in re.finditer(pattern, content):
            mime = match.group(1)
            b64 = match.group(2)
            ext = mime.split("/")[1] if "/" in mime else "png"
            try:
                images.append((base64.b64decode(b64), ext))
            except Exception:
                pass

    return images


def decode_data_url(url: str) -> tuple[bytes | None, str]:
    """Decode a data URL into bytes and file extension."""
    if not url.startswith("data:"):
        return None, "png"
    match = re.match(r'data:(image/\w+);base64,(.+)', url)
    if not match:
        return None, "png"
    mime = match.group(1)
    b64 = match.group(2)
    ext = mime.split("/")[1] if "/" in mime else "png"
    try:
        return base64.b64decode(b64), ext
    except Exception:
        return None, ext


def generate(prompt: str, model: str, ref_path: Path | None, size: str | None, api_key: str) -> dict:
    """Call OpenRouter API for image generation."""
    messages = build_messages(prompt, ref_path, size)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    print(f"Generating image with {model}...", file=sys.stderr)

    with httpx.Client(timeout=120.0) as client:
        response = client.post(OPENROUTER_API_URL, headers=headers, json=payload)

    if response.status_code != 200:
        print(f"API Error ({response.status_code}): {response.text}", file=sys.stderr)
        sys.exit(1)

    return response.json()


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    args = parse_args(sys.argv[1:])

    if not args["prompt"]:
        print("Error: No prompt specified", file=sys.stderr)
        sys.exit(1)

    ref_path = None
    if args["ref"]:
        ref_path = Path(args["ref"]).resolve()
        if not ref_path.exists():
            print(f"Error: Reference image not found: {ref_path}", file=sys.stderr)
            sys.exit(1)

    result = generate(
        prompt=args["prompt"],
        model=args["model"],
        ref_path=ref_path,
        size=args["size"],
        api_key=api_key,
    )

    images = extract_images(result)

    if not images:
        # Print whatever text the model returned for debugging
        message = result.get("choices", [{}])[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            content = "\n".join(texts)
        print(f"No image in response. Model output:\n{content}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args["output"]:
        output_base = Path(args["output"]).resolve()
    else:
        tmp_dir = find_tmp_dir(Path.cwd())
        tmp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_base = tmp_dir / f"imagine_{timestamp}.png"

    # Save images
    saved = []
    for i, (img_bytes, ext) in enumerate(images):
        if len(images) == 1:
            out_path = output_base.with_suffix(f".{ext}")
        else:
            out_path = output_base.with_stem(f"{output_base.stem}_{i}").with_suffix(f".{ext}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img_bytes)
        saved.append(out_path)
        print(f"Saved: {out_path}", file=sys.stderr)

    # Print paths to stdout for tool consumption
    for p in saved:
        print(p)


if __name__ == "__main__":
    main()
