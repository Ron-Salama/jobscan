# -*- coding: utf-8 -*-
"""Compatibility shim: the adapters now live in the sources/ package, one module per source.

jobscan.py imports this module (`import sources_ext as X`) and looks each adapter up by
name (getattr(X, "src_workday")); tests/test_rules.py imports it too. So every adapter
and shared helper of the old single-file module is re-exported here unchanged. New code
should import from `sources` directly.
"""
from sources import *  # noqa: F401,F403
from sources import (  # noqa: F401  (spelled out, so the full old API is visible here)
    ASHBY_BOARDS, _STUDENT_TITLE_RX, _is_student_title,
    src_ethosia, src_dialog, src_nisha, src_gotfriends, src_builtin, src_linkedin,
    src_cps, src_techjob, src_alljobs,
    src_comeet, src_workday, src_lever, src_ashby, src_moonactive, src_eightfold,
    src_oracle_hcm, src_smartrecruiters,
    src_apple, src_camtek, src_qualityai, src_lemonade, src_hibob, src_kaltura,
    src_google, src_checkpoint, src_meta, src_booking, src_sap, src_pwc,
)
