#!/usr/bin/env python3
"""Create an order-preserving prefix sample from a DiskANN .bin matrix."""

import argparse
import struct


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--count", type=int, required=True)
    args = parser.parse_args()

    with open(args.source, "rb") as src:
        nrows, dim = struct.unpack("<II", src.read(8))
        if not 0 < args.count <= nrows:
            raise ValueError(f"count must be in [1, {nrows}]")
        payload = src.read(args.count * dim * 4)
        if len(payload) != args.count * dim * 4:
            raise ValueError("truncated source matrix")

    with open(args.output, "wb") as dst:
        dst.write(struct.pack("<II", args.count, dim))
        dst.write(payload)
    print(f"wrote {args.count}x{dim} prefix sample to {args.output}")


if __name__ == "__main__":
    main()
