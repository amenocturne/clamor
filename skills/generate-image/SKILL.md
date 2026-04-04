---
name: generate-image
description: Image generation. Use when user asks to generate, create, draw, or visualize an image. Also use for image editing when a reference image is provided. Triggers on "generate image", "draw", "create picture", "visualize", "imagine", "image of".
author: amenocturne
---

# Generate Image

Generate images from text prompts via OpenRouter API with Gemini Flash Image.

> Run commands via justfile: `just -f <skill-path>/justfile <recipe> [flags]`

## Requirements

- `OPENROUTER_API_KEY` environment variable

## Recipes

### generate

```bash
just -f <skill-path>/justfile generate <prompt> [--ref=PATH] [--output=PATH] [--size=WxH] [--model=MODEL]
```

- `<prompt>`: Text description of the image (quoted if contains spaces)
- `--ref`: Reference image for editing or variation
- `--output`: Output file path (default: `<project-root>/tmp/imagine_<timestamp>.png`)
- `--size`: Desired dimensions hint, e.g. `1024x1024`
- `--model`: Override model (default: `google/gemini-3.1-flash-image-preview`)

**All paths must be absolute.** `just` runs from the justfile's directory.

## Workflow

1. Generate:
   ```bash
   just -f <skill-path>/justfile generate "a cat in a top hat, watercolor" --output=/project-root/tmp/cat.png
   ```

2. Read the output path printed to stdout to view the image

3. Iterate — edit with a reference:
   ```bash
   just -f <skill-path>/justfile generate "make the background a sunset" --ref=/project-root/tmp/cat.png --output=/project-root/tmp/cat_sunset.png
   ```

## Output

Prints generated image file paths to stdout (one per line). Read these paths to view the images.
