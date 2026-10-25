"""Draw the article's figures from results/*.json (needs matplotlib)."""

import json
import os
import sys
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.family"] = ["Hiragino Sans", "sans-serif"]
plt.rcParams["font.size"] = 11

INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
CRIT = "#c62828"


def load(name):
    return json.load(open(os.path.join(HERE, "results", f"{name}.json")))


def dlq_time(m):
    return datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")).timestamp()


def oldest_pending_age(d, step=0.1):
    """Age of the oldest record that is neither scored nor discarded, over time."""
    t0 = d["t0"]
    scored = {}
    for e in d["events"]:
        if e["kind"] == "scored":
            scored.setdefault(e["seq"], e["t"])
    discarded = {}
    for m in d["dlq"]:
        b = m["KinesisBatchInfo"]
        lo, hi = int(b["startSequenceNumber"]), int(b["endSequenceNumber"])
        for s in d["sent"]:
            if lo <= int(s["seq"]) <= hi:
                discarded.setdefault(s["seq"], dlq_time(m))
    items = []
    for s in d["sent"]:
        r = min(scored.get(s["seq"], float("inf")), discarded.get(s["seq"], float("inf")))
        items.append((s["t"], r))
    end = max(e["t"] for e in d["events"])
    xs, ys = [], []
    t = t0
    while t <= end:
        pend = [a for a, r in items if a <= t and r > t]
        xs.append(t - t0)
        ys.append(t - min(pend) if pend else 0.0)
        t += step
    return xs, ys


def style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_age():
    series = [
        ("default", "既定の設定", ORANGE),
        ("retry2", "MaximumRetryAttempts=2", BLUE),
        ("partial_all", "ReportBatchItemFailures（残りを処理）", AQUA),
    ]
    data = {name: oldest_pending_age(load(name)) for name, _, _ in series}
    d = load("default")
    poison_t = next(s["t"] for s in d["sent"] if s["kind"] == "poison") - d["t0"]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 7.2), dpi=150, gridspec_kw={"height_ratios": [3, 2]})
    for name, label, color in series:
        xs, ys = data[name]
        ax.plot(xs, ys, color=color, linewidth=2, label=label)
    ax.axvline(poison_t, color=MUTED, linewidth=1, linestyle="--")
    ax.text(poison_t + 4, 125, "20秒：壊れたイベントと\n不正な決済が届く", color=INK2, fontsize=10)
    ax.text(150, 210, "既定：先に進まない\n（286秒で観測を打ち切り）", color=INK, fontsize=10, ha="right")
    ax.set_ylabel("待ち時間（秒）", color=INK2)
    ax.set_title("未処理で残っている最も古いレコードの待ち時間（IteratorAge に相当する値を自分で計算）",
                 color=INK, loc="left", fontsize=11.5)
    ax.set_xlim(0, 300)
    ax.set_ylim(0, 280)
    style(ax)
    ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 0.05), labelcolor=INK)

    for name, label, color in series[1:]:
        xs, ys = data[name]
        ax2.plot(xs, ys, color=color, linewidth=2, label=label)
    ax2.axvline(poison_t, color=MUTED, linewidth=1, linestyle="--")
    ax2.set_xlim(0, 100)
    ax2.set_ylim(0, 3)
    ax2.set_title("上限ありの 2 つだけを拡大（横軸 0〜100 秒）", color=INK, loc="left", fontsize=11)
    ax2.set_ylabel("待ち時間（秒）", color=INK2)
    ax2.set_xlabel("実験開始からの経過時間（秒）", color=INK2)
    style(ax2)
    ax2.legend(frameon=False, loc="upper right", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "oldest-pending-age.png"))
    plt.close(fig)


def batches(d, max_attempts=None):
    """Invocations that touched the poison batch, with each record's fate."""
    order = [s["seq"] for s in d["sent"]]
    kind = {s["seq"]: s["kind"] for s in d["sent"]}
    poison_seq = next(s["seq"] for s in d["sent"] if s["kind"] == "poison")
    by_req = {}
    for e in d["events"]:
        if e["kind"] in ("scored", "poison"):
            by_req.setdefault(e["request_id"], {})[e["seq"]] = e["kind"]
    rows = []
    for e in sorted((e for e in d["events"] if e["kind"] == "invoke"), key=lambda e: e["t"]):
        i = order.index(e["first_seq"])
        seqs = order[i:i + e["batch_size"]]
        if poison_seq not in seqs:
            continue
        done = by_req.get(e["request_id"], {})
        cells = []
        for s in seqs:
            k = kind[s]
            if k == "poison":
                cells.append("poison")
            elif s in done:
                cells.append("fraud_hit" if k == "fraud" else "good_done")
            else:
                cells.append("fraud_skip" if k == "fraud" else "good_skip")
        rows.append((e["t"] - d["t0"], cells))
    return rows


def fig_batches():
    scen = [
        ("default", "既定の設定"),
        ("retry2", "MaximumRetryAttempts=2 ＋ 失敗時の送信先 SQS"),
        ("partial", "MaximumRetryAttempts=2 ＋ ReportBatchItemFailures（壊れた所で処理を止めて報告）"),
        ("partial_all", "MaximumRetryAttempts=2 ＋ ReportBatchItemFailures（残りを処理してから報告）"),
    ]
    colors = {
        "good_done": ("#d6e6f8", BLUE, ""),
        "good_skip": ("white", MUTED, ""),
        "poison": (INK2, INK2, "壊"),
        "fraud_hit": (CRIT, CRIT, "不正"),
        "fraud_skip": ("white", CRIT, "不正"),
    }
    fig, ax = plt.subplots(figsize=(10, 7.4), dpi=150)
    y = 0
    w, h, gap = 0.62, 0.62, 0.08
    for name, label in scen:
        d = load(name)
        rows = batches(d)
        ax.text(-4.3, -y - 0.3, label.replace("\n", " "), ha="left", va="center", fontsize=10,
                color=INK, fontweight="bold")
        y += 0.7
        for n, (t, cells) in enumerate(rows):
            if name == "default" and 3 <= n < len(rows) - 1:
                if n == 3:
                    ax.text(0.2, -y - 0.35, f"…（同じバッチを同じように失敗し続ける。計{len(rows)}回）",
                            color=INK2, fontsize=9, va="center")
                    y += 0.8
                continue
            for j, c in enumerate(cells):
                fc, ec, txt = colors[c]
                ax.add_patch(Rectangle((j * (w + gap), -y - h), w, h, facecolor=fc, edgecolor=ec, linewidth=1.2))
                if txt:
                    ax.text(j * (w + gap) + w / 2, -y - h / 2, txt, ha="center", va="center", fontsize=8,
                            color="white" if fc not in ("white",) else ec)
            ax.text(-0.25, -y - h / 2, f"{n + 1}回目 {t:6.1f}秒", ha="right", va="center", fontsize=9, color=INK2)
            y += 0.8
        if d["dlq"]:
            b = d["dlq"][0]["KinesisBatchInfo"]["batchSize"]
            ax.text(0.0, -y - 0.3, f"→ {b}件分の範囲を SQS へ（中身は入らずシーケンス番号だけ）",
                    color=INK, fontsize=9, va="center")
            y += 0.7
        else:
            ax.text(0.0, -y - 0.3, "→ 回数の上限なし。AWS ではレコードの期限が切れるまで続く", color=INK, fontsize=9, va="center")
            y += 0.7
        ax.axhline(-(y - 0.05), color=GRID, linewidth=0.8, xmin=0, xmax=1)
        y += 0.9
    # legend
    lx = 6.0
    for i, (c, lab) in enumerate([("good_done", "判定した決済"),
                                  ("poison", "壊れたイベント"), ("fraud_hit", "不正を検知"),
                                  ("fraud_skip", "不正な決済（未判定）")]):
        fc, ec, txt = colors[c]
        ax.add_patch(Rectangle((lx, -0.9 - i * 0.6), 0.4, 0.4, facecolor=fc, edgecolor=ec, linewidth=1.2))
        ax.text(lx + 0.55, -0.7 - i * 0.6, lab, va="center", fontsize=9, color=INK2)
    ax.set_xlim(-4.4, 9.5)
    ax.set_ylim(-y, 0.3)
    ax.axis("off")
    ax.set_title("壊れたイベントを含むバッチが、呼び出しごとにどう扱われたか（LocalStack の実測）",
                 color=INK, loc="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "poison-batch.png"))
    plt.close(fig)


if __name__ == "__main__":
    fig_age()
    fig_batches()
    print("wrote", OUT)
