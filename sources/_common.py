# -*- coding: utf-8 -*-
"""Helpers shared by several adapters."""

import re as _re_shared

# Shared student test for the free-text board adapters (audit 2026-09-24, BUG 9).
# TITLE ONLY, word-bound: JD/company-blurb text ("המתמחה בפיתוח" = "that specializes in
# development", "internal tools", "international") must never make a role 'student'.
# 'graduate' / 'בוגר' (graduate) mean junior, never student.
_STUDENT_TITLE_RX = _re_shared.compile(r"\b(student|interns?|internship|co-?op|trainee)\b", _re_shared.I)


def _is_student_title(title):
    t = title or ""
    return bool(_STUDENT_TITLE_RX.search(t)) or "סטודנט" in t or t.strip().startswith("מתמח")
