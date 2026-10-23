#!/usr/bin/env python3
"""Generate a `misc` image whose bootloader control block commands fastbootd.

The Android bootloader control block (BCB) starts at offset 0 of the `misc`
partition. Its `command` field is 32 bytes at offset 0. Writing the value
``boot-fastboot`` makes the bootloader boot *fastbootd* (userspace fastboot)
instead of the normal system.

On devices whose current A/B slot fails AVB verification, this gets you into
fastbootd running from the healthy slot; bootctl there marks that slot
``successful`` and makes it current, which un-breaks the next normal boot.

Example:
    python make_misc_fastboot.py -o misc_tofastbootd.img
    python make_misc_fastboot.py -o misc_recovery.img --command boot-recovery
"""

from __future__ import annotations

import argparse
import sys

BCB_COMMAND_LEN = 32
DEFAULT_SIZE = 8192  # two 4096-byte sectors, enough for the BCB


def build(command: str, size: int) -> bytes:
    encoded = command.encode("ascii")
    if len(encoded) >= BCB_COMMAND_LEN:
        raise ValueError(
            f"command must be shorter than {BCB_COMMAND_LEN} bytes, got {len(encoded)}"
        )
    if size < 4096:
        raise ValueError("image must be at least one 4096-byte sector")

    data = bytearray(size)
    data[0 : len(encoded)] = encoded
    return bytes(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a misc/BCB image to force a bootloader boot mode.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="misc_tofastbootd.img",
        help="output image path (default: misc_tofastbootd.img)",
    )
    parser.add_argument(
        "-c",
        "--command",
        default="boot-fastboot",
        help=(
            "BCB command. Useful values: boot-fastboot (fastbootd), "
            "boot-recovery (recovery), bootonce-bootloader (bootloader). "
            "Default: boot-fastboot"
        ),
    )
    parser.add_argument(
        "-s",
        "--size",
        type=int,
        default=DEFAULT_SIZE,
        help=f"image size in bytes (default: {DEFAULT_SIZE})",
    )
    args = parser.parse_args(argv)

    try:
        image = build(args.command, args.size)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with open(args.output, "wb") as handle:
        handle.write(image)

    print(f"wrote {args.output}")
    print(f"  size    : {len(image)} bytes")
    print(f"  command : {args.command!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
