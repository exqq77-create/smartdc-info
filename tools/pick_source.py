#!/usr/bin/env python3
"""Pick the least-used reference source for a topic, or log a use.

usage:
  python3 -I pick_source.py <sources_dir> pick <topic> [--n 1]
      → prints JSON list of candidates: id, file, keyword, body_chars, use_count
        (lowest use_count first, then longest body; exact duplicates and <500자 files skipped)
  python3 -I pick_source.py <sources_dir> log <source_id> <slug> <date> [note]
      → appends to usage-log.jsonl and updates catalog.json "used"
"""
import sys, json
from pathlib import Path

def load(d):
    c = json.loads((d / "catalog.json").read_text(encoding="utf-8"))
    return c

def main():
    d = Path(sys.argv[1]); cmd = sys.argv[2]
    cat = load(d)
    if cmd == "pick":
        topic = sys.argv[3]
        n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 1
        cands = [x for x in cat["items"] if x.get("topic") == topic and not x.get("exact_dup_of") and x.get("body_chars", 0) >= 500]
        cands.sort(key=lambda x: (len(x.get("used", [])), -x.get("body_chars", 0)))
        out = [{"id": x["id"], "file": x["file"], "keyword": x["keyword"], "body_chars": x["body_chars"], "use_count": len(x.get("used", []))} for x in cands[:n]]
        print(json.dumps({"topic": topic, "available": len(cands), "candidates": out}, ensure_ascii=False, indent=1))
    elif cmd == "log":
        sid, slug, date = sys.argv[3:6]; note = sys.argv[6] if len(sys.argv) > 6 else ""
        for x in cat["items"]:
            if x["id"] == sid:
                x.setdefault("used", []).append({"slug": slug, "date": date, "note": note}); break
        else:
            print("unknown source id", sid); sys.exit(1)
        (d / "catalog.json").write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
        with (d / "usage-log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"date": date, "source_id": sid, "source_file": x["file"], "original": x["original"], "slug": slug, "note": note}, ensure_ascii=False) + "\n")
        print("logged", sid, "->", slug)
    else:
        print(__doc__); sys.exit(2)

if __name__ == "__main__":
    main()
