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
    return int(matches[-1].replace(",", "")) if matches else -10**18


def run_variant(path: Path, days: list[str]) -> int:
    cmd = ["prosperity4btest", str(path), *days, "--data", "data", *LIMITS]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return parse_total(proc.stdout + proc.stderr)


def main():
    template = Path("trader_velvet_bot.py").read_text()
    outdir = Path("/tmp/velvet_passive_size")
    outdir.mkdir(exist_ok=True)

    rows = []
    combos = itertools.product(
        [25, 50, 75, 100, 150],
        [5, 10, 15, 20, 30],
        [100, 150, 200],
        [15, 30],
        [15, 30, 50],
    )
    for idx, (passive_cap, quote_size, mark_cap, mark_qsize, mark_ask_size) in enumerate(combos):
        src = template
        for name, value in [
            ("PASSIVE_CAP", passive_cap),
            ("QUOTE_SIZE", quote_size),
            ("MARK67_PASSIVE_CAP", mark_cap),
            ("MARK67_QUOTE_SIZE", mark_qsize),
            ("MARK67_ASK_CAP", mark_cap),
            ("MARK67_ASK_SIZE", mark_ask_size),
        ]:
            src = replace_const(src, name, value)
        path = outdir / f"trader_velvet_size_{idx}.py"
        path.write_text(src)
        train = run_variant(path, ["4-1", "4-2"])
        rows.append((train, idx, passive_cap, quote_size, mark_cap, mark_qsize, mark_ask_size, path))
        print(train, idx, passive_cap, quote_size, mark_cap, mark_qsize, mark_ask_size, flush=True)

    rows.sort(reverse=True)
    print("\\nTOP TRAIN")
    for row in rows[:12]:
        print(row[:-1])

    print("\\nTOP HOLDOUT")
    for row in rows[:12]:
        train, idx, passive_cap, quote_size, mark_cap, mark_qsize, mark_ask_size, path = row
        holdout = run_variant(path, ["4-3"])
        full = run_variant(path, ["4-1", "4-2", "4-3"])
        print((train, holdout, full, idx, passive_cap, quote_size, mark_cap, mark_qsize, mark_ask_size))


if __name__ == "__main__":
    main()
