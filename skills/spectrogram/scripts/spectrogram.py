# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "librosa>=0.10",
#     "matplotlib>=3.8",
#     "numpy>=1.24",
#     "soundfile>=0.12",
# ]
# ///
"""Generate spectrogram + waveform images from audio files for visual analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import librosa
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np


def load_audio(path: str, sr: int = 44100, mono: bool = True) -> tuple[np.ndarray, int]:
    y, sr_out = librosa.load(path, sr=sr, mono=mono)
    return y, sr_out


def chunk_audio(
    samples: np.ndarray,
    sr: int,
    chunk_secs: float = 60.0,
    overlap_secs: float = 0.5,
) -> list[tuple[np.ndarray, float, float]]:
    total_samples = samples.shape[-1]
    total_secs = total_samples / sr

    if total_secs <= chunk_secs:
        return [(samples, 0.0, total_secs)]

    chunks: list[tuple[np.ndarray, float, float]] = []
    nominal_start = 0.0

    while nominal_start < total_secs:
        actual_start = (
            max(0.0, nominal_start - overlap_secs) if nominal_start > 0 else 0.0
        )
        end = min(nominal_start + chunk_secs, total_secs)

        start_sample = int(actual_start * sr)
        end_sample = int(end * sr)

        if samples.ndim == 1:
            chunk_samples = samples[start_sample:end_sample]
        else:
            chunk_samples = samples[:, start_sample:end_sample]

        chunks.append((chunk_samples, actual_start, end))
        nominal_start += chunk_secs

    return chunks


def compute_spectrogram(
    samples: np.ndarray,
    sr: int,
    fmin: int = 20,
    fmax: int = 16000,
    top_db: int = 80,
) -> np.ndarray:
    # Scale mel bands to frequency range to avoid empty filters
    full_range_mels = librosa.hz_to_mel(16000) - librosa.hz_to_mel(20)
    actual_mels = librosa.hz_to_mel(fmax) - librosa.hz_to_mel(fmin)
    n_mels = max(32, int(256 * actual_mels / full_range_mels))

    S = librosa.feature.melspectrogram(
        y=samples,
        sr=sr,
        n_fft=4096,
        hop_length=512,
        n_mels=n_mels,
        fmin=fmin,
        fmax=fmax,
    )
    S_db = librosa.power_to_db(S, ref=np.max, top_db=top_db)
    return S_db


def compute_waveform_envelope(
    samples: np.ndarray, sr: int, target_width: int
) -> np.ndarray:
    total = len(samples)
    if target_width <= 0:
        return np.array([0.0])
    block_size = max(1, total // target_width)
    n_blocks = total // block_size
    trimmed = samples[: n_blocks * block_size].reshape(n_blocks, block_size)
    envelope = np.max(np.abs(trimmed), axis=1)
    return envelope


def format_time(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _nice_time_ticks(start_sec: float, end_sec: float) -> np.ndarray:
    duration = end_sec - start_sec
    nice_intervals = [1, 2, 5, 10, 15, 30, 60, 120, 300]
    target_ticks = 8
    raw = duration / target_ticks
    interval = next((i for i in nice_intervals if i >= raw), nice_intervals[-1])

    first = int(start_sec) + (interval - int(start_sec) % interval) % interval
    return np.arange(first, int(end_sec) + 1, interval)


def _setup_figure_style(fig: plt.Figure) -> None:
    fig.patch.set_facecolor("#0a0a0a")


def _get_freq_ticks(fmin: int, fmax: int, n_mels: int) -> tuple[list[float], list[str]]:
    reference_freqs = [
        100,
        300,
        500,
        700,
        1000,
        1500,
        2000,
        3000,
        5000,
        7000,
        10000,
        15000,
    ]
    freqs = [f for f in reference_freqs if fmin <= f <= fmax]

    labels = []
    for f in freqs:
        if f >= 1000:
            labels.append(f"{f // 1000}k" if f % 1000 == 0 else f"{f / 1000:.1f}k")
        else:
            labels.append(str(f))

    mel_min = librosa.hz_to_mel(fmin)
    mel_max = librosa.hz_to_mel(fmax)

    positions = []
    for f in freqs:
        mel_val = librosa.hz_to_mel(f)
        pos = (mel_val - mel_min) / (mel_max - mel_min) * n_mels
        positions.append(pos)

    return positions, labels


def _render_spectrogram_ax(
    ax: plt.Axes,
    spec: np.ndarray,
    sr: int,
    start_sec: float,
    end_sec: float,
    fmin: int,
    fmax: int,
    overlap_start: bool,
    overlap_end: bool,
    overlap_secs: float,
    show_xlabel: bool,
    label: str | None = None,
) -> plt.cm.ScalarMappable:
    n_mels = spec.shape[0]
    img = ax.imshow(
        spec,
        aspect="auto",
        origin="lower",
        cmap="inferno",
        extent=[start_sec, end_sec, 0, n_mels],
    )

    positions, labels = _get_freq_ticks(fmin, fmax, n_mels)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=7, color="#cccccc")
    ax.tick_params(axis="y", colors="#cccccc", length=3)

    time_ticks = _nice_time_ticks(start_sec, end_sec)
    ax.set_xticks(time_ticks)
    if show_xlabel:
        ax.set_xticklabels(
            [format_time(t) for t in time_ticks], fontsize=7, color="#cccccc"
        )
    else:
        ax.set_xticklabels([])
    ax.tick_params(axis="x", colors="#cccccc", length=3)

    ax.set_facecolor("#0a0a0a")
    for spine in ax.spines.values():
        spine.set_color("#333333")

    if overlap_start:
        ax.axvspan(start_sec, start_sec + overlap_secs, color="red", alpha=0.2)
    if overlap_end:
        ax.axvspan(end_sec - overlap_secs, end_sec, color="red", alpha=0.2)

    if label:
        ax.text(
            0.005,
            0.95,
            label,
            transform=ax.transAxes,
            fontsize=9,
            color="#cccccc",
            va="top",
            ha="left",
            fontweight="bold",
        )

    return img


def _render_waveform_ax(
    ax: plt.Axes,
    envelope: np.ndarray,
    start_sec: float,
    end_sec: float,
    overlap_start: bool,
    overlap_end: bool,
    overlap_secs: float,
    show_xlabel: bool,
    label: str | None = None,
) -> None:
    time_axis = np.linspace(start_sec, end_sec, len(envelope))
    db_envelope = 20 * np.log10(np.abs(envelope) + 1e-10)

    ax.fill_between(
        time_axis, db_envelope, -60, color="#ff6600", alpha=0.7, linewidth=0
    )
    ax.plot(time_axis, db_envelope, color="#ff8833", linewidth=0.5, alpha=0.8)

    ax.set_ylim(-35, 0)
    ax.set_xlim(start_sec, end_sec)
    ax.set_yticks([0, -10, -20, -30])
    ax.set_yticklabels(["0", "-10", "-20", "-30"], fontsize=6, color="#cccccc")
    ax.tick_params(axis="y", colors="#cccccc", length=2)

    time_ticks = _nice_time_ticks(start_sec, end_sec)
    ax.set_xticks(time_ticks)
    if show_xlabel:
        ax.set_xticklabels(
            [format_time(t) for t in time_ticks], fontsize=7, color="#cccccc"
        )
    else:
        ax.set_xticklabels([])
    ax.tick_params(axis="x", colors="#cccccc", length=3)

    ax.set_facecolor("#0a0a0a")
    for spine in ax.spines.values():
        spine.set_color("#333333")

    if overlap_start:
        ax.axvspan(start_sec, start_sec + overlap_secs, color="red", alpha=0.2)
    if overlap_end:
        ax.axvspan(end_sec - overlap_secs, end_sec, color="red", alpha=0.2)

    if label:
        ax.text(
            0.005,
            0.9,
            label,
            transform=ax.transAxes,
            fontsize=7,
            color="#cccccc",
            va="top",
            ha="left",
            fontweight="bold",
        )


def render_mono(
    spec: np.ndarray,
    waveform: np.ndarray,
    sr: int,
    start_sec: float,
    end_sec: float,
    output_path: str,
    px_per_sec: int = 25,
    fmin: int = 20,
    fmax: int = 16000,
    overlap_start: bool = False,
    overlap_end: bool = False,
    overlap_secs: float = 0.5,
) -> None:
    duration = end_sec - start_sec
    fig_width = duration * px_per_sec / 100
    fig_width = max(fig_width, 4.0)
    fig_height = 7.0
    dpi = 100

    fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
    _setup_figure_style(fig)

    gs = gridspec.GridSpec(2, 1, height_ratios=[85, 15], hspace=0.08, figure=fig)

    ax_spec = fig.add_subplot(gs[0])
    img = _render_spectrogram_ax(
        ax_spec,
        spec,
        sr,
        start_sec,
        end_sec,
        fmin,
        fmax,
        overlap_start,
        overlap_end,
        overlap_secs,
        show_xlabel=False,
    )

    cbar = fig.colorbar(img, ax=ax_spec, fraction=0.015, pad=0.01)
    cbar.ax.tick_params(labelsize=6, colors="#cccccc", length=2)
    cbar.set_label("dB", fontsize=7, color="#cccccc")
    cbar.outline.set_edgecolor("#333333")

    ax_wave = fig.add_subplot(gs[1], sharex=ax_spec)
    _render_waveform_ax(
        ax_wave,
        waveform,
        start_sec,
        end_sec,
        overlap_start,
        overlap_end,
        overlap_secs,
        show_xlabel=True,
    )
    ax_wave.set_ylabel("dBFS", fontsize=7, color="#cccccc", labelpad=2)

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="#0a0a0a")
    plt.close(fig)


def render_stereo(
    spec_l: np.ndarray,
    spec_r: np.ndarray,
    waveform_l: np.ndarray,
    waveform_r: np.ndarray,
    sr: int,
    start_sec: float,
    end_sec: float,
    output_path: str,
    px_per_sec: int = 25,
    fmin: int = 20,
    fmax: int = 16000,
    overlap_start: bool = False,
    overlap_end: bool = False,
    overlap_secs: float = 0.5,
) -> None:
    duration = end_sec - start_sec
    fig_width = duration * px_per_sec / 100
    fig_width = max(fig_width, 4.0)
    fig_height = 9.0
    dpi = 100

    fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
    _setup_figure_style(fig)

    gs = gridspec.GridSpec(4, 1, height_ratios=[42, 42, 8, 8], hspace=0.08, figure=fig)

    ax_spec_l = fig.add_subplot(gs[0])
    img_l = _render_spectrogram_ax(
        ax_spec_l,
        spec_l,
        sr,
        start_sec,
        end_sec,
        fmin,
        fmax,
        overlap_start,
        overlap_end,
        overlap_secs,
        show_xlabel=False,
        label="L",
    )
    cbar_l = fig.colorbar(img_l, ax=ax_spec_l, fraction=0.015, pad=0.01)
    cbar_l.ax.tick_params(labelsize=6, colors="#cccccc", length=2)
    cbar_l.set_label("dB", fontsize=7, color="#cccccc")
    cbar_l.outline.set_edgecolor("#333333")

    ax_spec_r = fig.add_subplot(gs[1], sharex=ax_spec_l)
    img_r = _render_spectrogram_ax(
        ax_spec_r,
        spec_r,
        sr,
        start_sec,
        end_sec,
        fmin,
        fmax,
        overlap_start,
        overlap_end,
        overlap_secs,
        show_xlabel=False,
        label="R",
    )
    cbar_r = fig.colorbar(img_r, ax=ax_spec_r, fraction=0.015, pad=0.01)
    cbar_r.ax.tick_params(labelsize=6, colors="#cccccc", length=2)
    cbar_r.set_label("dB", fontsize=7, color="#cccccc")
    cbar_r.outline.set_edgecolor("#333333")

    ax_wave_l = fig.add_subplot(gs[2], sharex=ax_spec_l)
    _render_waveform_ax(
        ax_wave_l,
        waveform_l,
        start_sec,
        end_sec,
        overlap_start,
        overlap_end,
        overlap_secs,
        show_xlabel=False,
        label="L",
    )

    ax_wave_r = fig.add_subplot(gs[3], sharex=ax_spec_l)
    _render_waveform_ax(
        ax_wave_r,
        waveform_r,
        start_sec,
        end_sec,
        overlap_start,
        overlap_end,
        overlap_secs,
        show_xlabel=True,
        label="R",
    )
    ax_wave_r.set_ylabel("dBFS", fontsize=7, color="#cccccc", labelpad=2)

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="#0a0a0a")
    plt.close(fig)


def _format_chunk_time(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}m{secs:02d}s"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate spectrogram images from audio files."
    )
    parser.add_argument("audio_file", help="Path to audio file")
    parser.add_argument("--output", help="Output directory for PNGs")
    parser.add_argument(
        "--stereo", action="store_true", help="Generate stereo L/R spectrograms"
    )
    parser.add_argument("--start", type=float, default=0, help="Start time in seconds")
    parser.add_argument("--end", type=float, default=None, help="End time in seconds")
    parser.add_argument(
        "--chunk", type=float, default=60, help="Chunk duration in seconds"
    )
    parser.add_argument("--no-chunk", action="store_true", help="Force single image")
    parser.add_argument("--px-per-sec", type=int, default=25, help="Pixels per second")
    parser.add_argument("--fmin", type=int, default=20, help="Min frequency in Hz")
    parser.add_argument("--fmax", type=int, default=16000, help="Max frequency in Hz")
    parser.add_argument("--top-db", type=int, default=80, help="Dynamic range in dB")
    args = parser.parse_args()

    audio_path = Path(args.audio_file)
    if not audio_path.exists():
        print(f"Error: file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    stem = audio_path.stem
    mono = not args.stereo

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = audio_path.parent

    print(f"Loading {audio_path.name}...", file=sys.stderr)
    y, sr = load_audio(str(audio_path), mono=mono)

    total_duration = y.shape[-1] / sr

    start = args.start
    end = args.end if args.end is not None else total_duration
    end = min(end, total_duration)

    if start >= end:
        print(f"Error: start ({start}s) >= end ({end}s)", file=sys.stderr)
        sys.exit(1)

    start_sample = int(start * sr)
    end_sample = int(end * sr)
    if y.ndim == 1:
        y = y[start_sample:end_sample]
    else:
        y = y[:, start_sample:end_sample]

    if args.no_chunk:
        chunks = [(y, start, end)]
    else:
        chunks = chunk_audio(y, sr, chunk_secs=args.chunk)
        # Adjust chunk times to absolute positions
        chunks = [(c, s + start, e + start) for c, s, e in chunks]

    n_chunks = len(chunks)
    output_paths: list[str] = []

    for i, (chunk_samples, chunk_start, chunk_end) in enumerate(chunks):
        if n_chunks > 1:
            print(
                f"Generating chunk {i + 1}/{n_chunks} ({format_time(chunk_start)} - {format_time(chunk_end)})...",
                file=sys.stderr,
            )
            time_label = (
                f"{_format_chunk_time(chunk_start)}-{_format_chunk_time(chunk_end)}"
            )
            filename = f"{stem}_chunk{i + 1:02d}_{time_label}.png"
        else:
            print("Generating spectrogram...", file=sys.stderr)
            filename = f"{stem}.png"

        output_path = str(out_dir / filename)

        overlap_start = i > 0
        overlap_end = i < n_chunks - 1

        if mono:
            spec = compute_spectrogram(
                chunk_samples, sr, fmin=args.fmin, fmax=args.fmax, top_db=args.top_db
            )
            fig_width_px = (chunk_end - chunk_start) * args.px_per_sec
            target_width = max(int(fig_width_px), 100)
            envelope = compute_waveform_envelope(chunk_samples, sr, target_width)

            render_mono(
                spec,
                envelope,
                sr,
                chunk_start,
                chunk_end,
                output_path,
                px_per_sec=args.px_per_sec,
                fmin=args.fmin,
                fmax=args.fmax,
                overlap_start=overlap_start,
                overlap_end=overlap_end,
            )
        else:
            left = chunk_samples[0]
            right = chunk_samples[1]

            spec_l = compute_spectrogram(
                left, sr, fmin=args.fmin, fmax=args.fmax, top_db=args.top_db
            )
            spec_r = compute_spectrogram(
                right, sr, fmin=args.fmin, fmax=args.fmax, top_db=args.top_db
            )

            fig_width_px = (chunk_end - chunk_start) * args.px_per_sec
            target_width = max(int(fig_width_px), 100)
            envelope_l = compute_waveform_envelope(left, sr, target_width)
            envelope_r = compute_waveform_envelope(right, sr, target_width)

            render_stereo(
                spec_l,
                spec_r,
                envelope_l,
                envelope_r,
                sr,
                chunk_start,
                chunk_end,
                output_path,
                px_per_sec=args.px_per_sec,
                fmin=args.fmin,
                fmax=args.fmax,
                overlap_start=overlap_start,
                overlap_end=overlap_end,
            )

        output_paths.append(output_path)

    for p in output_paths:
        print(p)

    print(f"Done. Generated {len(output_paths)} image(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
