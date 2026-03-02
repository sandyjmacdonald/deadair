#!/usr/bin/env python3
"""Entry point for the physical radio — loads config and wires up GPIO buttons."""
import argparse

from radio.config import load_config
from radio.input import GpioButtonInput
from radio.radio import RadioApp

DEFAULT_CONFIG = "/home/radio/deadair/config.toml"

BTN_DOWN = 5
BTN_UP = 6


def main() -> None:
    ap = argparse.ArgumentParser(description="Dead Air — FM radio simulator")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help=f"Path to config.toml (default: {DEFAULT_CONFIG})")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--verbose", action="store_true", help="Verbose output: timestamps, full paths, dial position")
    group.add_argument("--quiet", action="store_true", help="Suppress all non-error output")
    args = ap.parse_args()

    verbosity = "verbose" if args.verbose else "quiet" if args.quiet else "normal"

    cfg = load_config(args.config)
    app = RadioApp(
        config=cfg,
        inputs=[GpioButtonInput(BTN_DOWN, BTN_UP, cfg.step)],
        verbosity=verbosity,
    )
    app.run()


if __name__ == "__main__":
    main()
