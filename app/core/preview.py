"""Before/after previews. Rows that a step changed or removed are shown first so the effect is visible."""
from __future__ import annotations

import pandas as pd

from .. import config

_SCAN_ROWS = 20_000      # how far down the table we look for affected rows (keeps big files quick)


def _text(v) -> str | None:
    return None if pd.isna(v) else str(v)


def _same(a, b) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    return str(a) == str(b)


def _affected_index(before: pd.DataFrame, after: pd.DataFrame, cols: list[str]) -> list:
    head = before.iloc[:_SCAN_ROWS]
    affected = []
    in_after = head.index.isin(after.index)
    for idx in head.index[~in_after]:
        affected.append(idx)
    kept = head.index[in_after]
    if len(kept) and cols:
        b = head.loc[kept, cols]
        a = after.loc[kept, cols]
        differs = ~((b == a) | (b.isna() & a.isna()))
        affected.extend(kept[differs.any(axis=1).to_numpy()].tolist())
    return sorted(affected)


def _rows(frame: pd.DataFrame, other: pd.DataFrame, cols: list[str], index: list) -> list[dict]:
    out = []
    for idx in index:
        removed = idx not in other.index
        changed: list[int] = []
        if idx in frame.index and not removed:
            row, orow = frame.loc[idx, cols], other.loc[idx, cols]
            changed = [j for j, c in enumerate(cols) if not _same(row[c], orow[c])]
        values = [_text(frame.loc[idx, c]) for c in cols] if idx in frame.index else []
        out.append({"row": int(idx) + 1, "cells": values, "changed": changed, "removed": removed})
    return out


def preview_pair(before: pd.DataFrame, after: pd.DataFrame, n: int | None = None) -> dict:
    n = n or config.PREVIEW_ROWS
    cols = list(before.columns)
    shown = cols[: config.MAX_PREVIEW_COLS]
    affected = _affected_index(before, after, [c for c in cols if c in after.columns])
    if affected:
        mode, picked = "changed", affected[:n]
    else:
        mode, picked = "first", before.index[:n].tolist()
    after_picked = [i for i in picked if i in after.index]
    if mode == "first":
        after_picked = after.index[:n].tolist()
    return {
        "mode": mode,
        "columns": shown,
        "columns_hidden": max(0, len(cols) - len(shown)),
        "before": _rows(before, after, shown, picked),
        "after": _rows(after, before, shown, after_picked),
        "total_before": int(len(before)),
        "total_after": int(len(after)),
    }


def simple_preview(df: pd.DataFrame, n: int | None = None) -> dict:
    n = n or config.PREVIEW_ROWS
    cols = list(df.columns)[: config.MAX_PREVIEW_COLS]
    rows = [{"row": int(i) + 1, "cells": [_text(df.loc[i, c]) for c in cols], "changed": [], "removed": False}
            for i in df.index[:n]]
    return {"columns": cols, "columns_hidden": max(0, df.shape[1] - len(cols)), "rows": rows, "total": int(len(df))}
