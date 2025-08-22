from __future__ import annotations

import argparse
import sys
from difflib import get_close_matches


class SmartParser(argparse.ArgumentParser):
    def error(self, message: str):
        # Detect "invalid choice: 'foo' (choose from ...)"
        if "invalid choice" in message and "choose from" in message:
            bad = message.split("invalid choice:")[1].split("(")[0].strip().strip("'\"")
            choices_str = message.split("choose from")[1]
            choices = [c.strip().strip(",)'") for c in choices_str.split() if c.strip(",)")]

            tips = get_close_matches(bad, choices, n=3, cutoff=0.6)
            if tips:
                message += f"\n\nDid you mean: {', '.join(tips)}?"
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def cli(argv=None):
    p = SmartParser(prog="mycli")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ["init", "install", "inspect", "index"]:
        sp = sub.add_parser(name)
        sp.set_defaults(func=lambda args, n=name: print(f"ran {n}"))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    cli()
