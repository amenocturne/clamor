# /// script
# requires-python = ">=3.11"
# dependencies = ["click", "pillow", "numpy"]
# ///
"""Visual regression testing for canvas/WebGL content."""

import sys
from pathlib import Path

import click
import numpy as np
from PIL import Image


def compare_images(baseline_path: Path, current_path: Path) -> tuple[float, np.ndarray | None]:
    """
    Compare two images pixel-by-pixel.
    Returns (difference_percentage, diff_image_array).
    """
    baseline = Image.open(baseline_path).convert("RGBA")
    current = Image.open(current_path).convert("RGBA")

    # Resize current to match baseline if needed
    if baseline.size != current.size:
        current = current.resize(baseline.size, Image.Resampling.LANCZOS)

    baseline_arr = np.array(baseline, dtype=np.float32)
    current_arr = np.array(current, dtype=np.float32)

    # Calculate per-pixel difference
    diff = np.abs(baseline_arr - current_arr)
    diff_magnitude = np.sqrt(np.sum(diff[:, :, :3] ** 2, axis=2))  # RGB only, ignore alpha

    # Normalize to 0-1 range (max possible diff is sqrt(3 * 255^2) ≈ 441.67)
    max_diff = np.sqrt(3 * 255**2)
    diff_normalized = diff_magnitude / max_diff

    # Calculate percentage of pixels that differ
    threshold = 0.01  # Ignore tiny differences (< 1% of max)
    different_pixels = np.sum(diff_normalized > threshold)
    total_pixels = diff_normalized.size
    diff_percentage = (different_pixels / total_pixels) * 100

    # Create diff visualization
    diff_image = np.zeros((*baseline_arr.shape[:2], 4), dtype=np.uint8)
    diff_image[:, :, 0] = np.clip(diff_normalized * 255, 0, 255).astype(np.uint8)  # Red channel
    diff_image[:, :, 3] = np.where(diff_normalized > threshold, 255, 50).astype(np.uint8)  # Alpha

    return diff_percentage, diff_image


@click.command()
@click.argument("baseline", type=click.Path(exists=True, path_type=Path))
@click.argument("current", type=click.Path(exists=True, path_type=Path))
@click.option("--threshold", "-t", type=float, default=1.0, help="Max allowed difference percentage")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output diff image path")
@click.option("--json/--text", "json_output", default=False, help="Output format")
def main(baseline: Path, current: Path, threshold: float, output: Path | None, json_output: bool):
    """
    Compare two images for visual regression testing.

    Returns exit code 0 if difference is within threshold, 1 otherwise.

    Example:
        visual_diff.py baseline.png current.png --threshold 1 --output diff.png
    """
    diff_percentage, diff_image = compare_images(baseline, current)

    passed = diff_percentage <= threshold

    if output and diff_image is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(diff_image, mode="RGBA").save(output)

    if json_output:
        import json

        result = {
            "baseline": str(baseline),
            "current": str(current),
            "difference_percent": round(diff_percentage, 3),
            "threshold": threshold,
            "passed": passed,
            "diff_image": str(output) if output else None,
        }
        click.echo(json.dumps(result, indent=2))
    else:
        status = "PASS" if passed else "FAIL"
        click.echo(f"{status}: {diff_percentage:.2f}% different (threshold: {threshold}%)")

        if output:
            click.echo(f"Diff image saved to: {output}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
