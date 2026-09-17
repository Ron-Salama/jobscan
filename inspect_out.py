# -*- coding: utf-8 -*-
import json, io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
p = r"C:\Users\User\Desktop\Ron - Job Tracker (AUTO).html"
lines = open(p, encoding="utf-8").readlines()
line = lines[140]; s = line.index("[")
d = 0; e = None; instr = False; esc = False
for i in range(s, len(line)):
    c = line[i]
    if instr:
        if esc: esc = False
        elif c == "\\": esc = True
        elif c == '"': instr = False
        continue
    if c == '"': instr = True
    elif c == "[": d += 1
    elif c == "]":
        d -= 1
        if d == 0: e = i + 1; break
arr = json.loads(line[s:e])
print("rows:", len(arr))
print("by region:", dict(collections.Counter(r["region"] for r in arr)))
print("by fit:", dict(collections.Counter(r["fit"] for r in arr)))
src = collections.Counter()
for r in arr:
    note = r["openings"]["note"]
    if "sources:" in note:
        for s2 in note.split("sources:")[1].split("|")[0].split("+"):
            src[s2.strip()] += 1
print("by source:", dict(src))
print("\n--- REFERRAL / GIANT flagged ---")
for r in arr:
    if "REFERRAL" in r["openings"]["note"] or "GIANT" in r["openings"]["note"]:
        print("  [%s f%d] %s — %s" % (r["region"], r["fit"], r["company"], r["role"][:55]))
print("\n--- sample NORTH ---")
for r in [x for x in arr if x["region"] == "North"][:18]:
    print("  %-24s — %s" % (r["company"][:24], r["role"][:55]))
print("\n--- sample CENTER (first 12) ---")
for r in [x for x in arr if x["region"] == "Center"][:12]:
    print("  %-24s — %s" % (r["company"][:24], r["role"][:55]))
