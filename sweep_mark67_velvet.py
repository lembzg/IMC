import itertools
import re
import subprocess
from pathlib import Path


LIMITS = [
    "--limit", "VELVETFRUIT_EXTRACT:200",
    "--limit", "HYDROGEL_PACK:200",
    "--limit", "VEV_4000:300",
    "--limit", "VEV_4500:300",
    "--limit", "VEV_5000:300",
    "--limit", "VEV_5100:300",
    "--limit", "VEV_5200:300",
    "--limit", "VEV_5300:300",
    "--limit", "VEV_5400:300",
    "--limit", "VEV_5500:300",
    "--limit", "VEV_6000:300",
    "--limit", "VEV_6500:300",
]


def replace_const(src: str, name: str, value: int) -> str:
    return re.sub(rf"^{name}\s*=.*$", f"{name} = {value}", src, flags=re.MULTILINE)


def parse_total(output: str) -> int:
    matches = re.findall(r"Total profit:\s*(-?[\d,]+)", output)
    if not matches:
        return -10**18
    return int(matches[-1].replace(",", ""))


def run_variant(path: Path, days: list[str]) -> int:
    cmd = ["prosperity4btest", str(path), *days, "--data", "data", *LIMITS]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return parse_total(proc.stdout + proc.stderr)


def main():
    template = Path("trader_velvet_bot.py").read_text()
    outdir = Path("/tmp/mark67_sweep")
    outdir.mkdir(exist_ok=True)

    rows = []
    combos = itertools.product(
        [2000, 5000, 10000],
        [1, 2],
        [50, 200],
        [15, 30],
        [50, 200],
        [15, 50],
    )
    for idx, (window, skew, bid_cap, bid_size, ask_cap, ask_size) in enumerate(combos):
        src = template
        for name, value in [
            ("MARK67_WINDOW_TS", window),
            ("MARK67_SKEW_TICKS", skew),
            ("MARK67_PASSIVE_CAP", bid_cap),
            ("MARK67_QUOTE_SIZE", bid_size),
            ("MARK67_ASK_CAP", ask_cap),
            ("MARK67_ASK_SIZE", ask_size),
        ]:
            src = replace_const(src, name, value)
        path = outdir / f"trader_mark67_{idx}.py"
        path.write_text(src)
        train = run_variant(path, ["4-1", "4-2"])
        rows.append((train, idx, window, skew, bid_cap, bid_size, ask_cap, ask_size, path))
        print(train, idx, window, skew, bid_cap, bid_size, ask_cap, ask_size, flush=True)

    rows.sort(reverse=True)
    print("\nTOP TRAIN")
    for row in rows[:10]:
        print(row[:-1])

    print("\nTOP HOLDOUT")
    for row in rows[:10]:
        train, idx, window, skew, bid_cap, bid_size, ask_cap, ask_size, path = row
        holdout = run_variant(path, ["4-3"])
        full = run_variant(path, ["4-1", "4-2", "4-3"])
        print((train, holdout, full, idx, window, skew, bid_cap, bid_size, ask_cap, ask_size))


if __name__ == "__main__":
    main()
