"""Rebuild the generated sections of an existing report from its turns.jsonl: «Top 5 places attention dropped» and the
feelings as changes. Everything else in report.md (header, end answers, hand-written findings) stays as it is.

    python -X utf8 rereport.py <run dir> [<run dir> ...]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import jev_if_player as jp


def rebuild(run):
    run = Path(run)
    rows = [json.loads(x) for x in (run / "turns.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    text = (run / "report.md").read_text(encoding="utf-8")
    m = re.search(r"run ended: (.*)", text)
    ending = m.group(1) if m else ""
    c = Counter(r["mood"] for r in rows)
    new = "\n".join(jp.attention_lines(rows, ending) + [
        "## Feelings over the run", "", "Changes: " + (jp.arc(rows) or "—"), "",
        "Totals: " + " · ".join(f"{k} ×{n}" for k, n in c.most_common()), "", ""])
    text = re.sub(r"## Top 5 places attention dropped\n.*?(?=## Feelings over the run)", "", text, flags=re.S)
    text = re.sub(r"## Feelings over the run\n.*?(?=\n## )", new.rstrip("\n") + "\n", text, count=1, flags=re.S)
    (run / "report.md").write_text(text, encoding="utf-8")
    return len(jp.attention_drops(rows, ending))


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(d, "drops:", rebuild(d))
