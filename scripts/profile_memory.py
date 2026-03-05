#!/usr/bin/env python3
"""Simple runtime memory profiler for Pypboy.

Example:
    ./.venv/bin/python scripts/profile_memory.py --radio-seconds 20
"""

from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from datetime import datetime
from dataclasses import dataclass


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@dataclass
class Sample:
    t: float
    rss_kb: int
    module: str


def current_rss_kb() -> int:
    """Return current resident set size in KiB."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    # Format: VmRSS:   123456 kB
                    return int(line.split()[1])
    except Exception:
        pass
    # Fallback to max RSS if /proc is unavailable.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def pump_for(boy, seconds: float, samples: list[Sample], module_name: str) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for event in __import__("pygame").event.get():
            boy.handle_event(event)
        boy.render()
        samples.append(Sample(time.monotonic(), current_rss_kb(), module_name))


def format_mb(kb: int) -> str:
    return f"{kb / 1024:.2f} MB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile pypboy runtime memory usage.")
    parser.add_argument("--module-seconds", type=float, default=1.8, help="Seconds to stay on each module.")
    parser.add_argument("--radio-seconds", type=float, default=12.0, help="Extra seconds on radio module.")
    parser.add_argument(
        "--use-dummy-drivers",
        action="store_true",
        help="Set SDL_AUDIODRIVER/SDL_VIDEODRIVER to dummy for headless runs.",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Write report to this file. Default: modules/data/logs/memory_profile_<timestamp>.log",
    )
    args = parser.parse_args()

    if args.use_dummy_drivers:
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    os.chdir(PROJECT_ROOT)

    import pygame  # imported after optional env overrides
    import settings
    from pypboy.core import Pypboy

    # Match main.py behavior.
    try:
        pygame.mixer.pre_init(44100, -16, 1, 4096)
        settings.SOUND_ENABLED = True
    except Exception:
        settings.SOUND_ENABLED = False
    settings.GPIO_AVAILABLE = getattr(settings, "GPIO_AVAILABLE", False)

    samples: list[Sample] = []
    boot_t0 = time.monotonic()
    boy = Pypboy("Pip-Boy 3000 MK IV", settings.WIDTH, settings.HEIGHT)
    samples.append(Sample(time.monotonic(), current_rss_kb(), "startup"))

    order = ["boot", "stats", "items", "data", "map", "radio"]
    for module_name in order:
        boy.switch_module(module_name)
        pump_for(boy, args.module_seconds, samples, module_name)

    # Optionally keep radio active longer to include waveform/music allocations.
    if args.radio_seconds > 0:
        radio_mod = boy.get_module("radio")
        if radio_mod and hasattr(radio_mod, "stations") and radio_mod.stations:
            try:
                radio_mod.select_station(settings.STATION)
            except Exception:
                pass
        pump_for(boy, args.radio_seconds, samples, "radio_long")

    peak_ru_kb = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    peak_sample = max(samples, key=lambda s: s.rss_kb) if samples else None
    elapsed = time.monotonic() - boot_t0

    lines: list[str] = []
    lines.append("=== Pypboy Memory Profile ===")
    lines.append(f"elapsed={elapsed:.2f}s")
    if peak_sample:
        lines.append(
            "peak_current_rss=%d KB (%s) module=%s"
            % (peak_sample.rss_kb, format_mb(peak_sample.rss_kb), peak_sample.module)
        )
    final_rss = current_rss_kb()
    lines.append(f"peak_ru_maxrss={peak_ru_kb} KB ({format_mb(peak_ru_kb)})")
    lines.append(f"final_rss={final_rss} KB ({format_mb(final_rss)})")
    lines.append(f"sound_enabled={settings.SOUND_ENABLED}")
    lines.append(f"cwd={os.getcwd()}")
    lines.append(f"root={settings.ROOT_DIR}")

    if args.log_file:
        log_path = os.path.abspath(args.log_file)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(
            PROJECT_ROOT, "pypboy", "modules", "data", "logs", f"memory_profile_{stamp}.log"
        )
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    for line in lines:
        print(line)
    print(f"log_file={log_path}")

    try:
        pygame.mixer.quit()
    except Exception:
        pass
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
