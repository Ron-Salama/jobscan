# -*- coding: utf-8 -*-
"""Job-source adapters for JobScan, one module per source.

Each adapter is a function ``src_<name>()`` that fetches one site and returns a list of
row dicts. jobscan.collect() calls every registered adapter inside its own try/except,
then jobscan.normalize() fills any missing keys, so one broken site cannot stop a scan.
Row keys: source, sid, title, company, city, url, level, years_min, years_max, tech,
desc, active.

Adapter families:
  Job boards and staffing agencies:
      ethosia, dialog, nisha, gotfriends, builtin, linkedin, alljobs, cps*, techjob*
  ATS platforms (one adapter serves many companies):
      comeet, workday, lever, ashby, eightfold (Qualcomm, Microsoft),
      oracle_hcm (Oracle, Dell), smartrecruiters (Wix, SanDisk)
  Single-company career sites:
      apple, camtek, qualityai, lemonade, hibob, kaltura*, google, checkpoint, meta,
      booking, sap, pwc
  (* kept in the package but not registered in jobscan._EXT_NAMES; src_moonactive is a
  wrapper around src_ashby, which replaced it.)

The open-API sources (hiremetech, Experis, Drushim, Greenhouse, amazon.jobs) live in
jobscan.py itself. Which adapters actually run is decided by jobscan._EXT_NAMES.

History: until 2026-10-04 all of these lived in one 7,180-line sources_ext.py. They were
moved here with their function bodies unchanged, and sources_ext.py now re-exports them.
"""

from ._common import _STUDENT_TITLE_RX, _is_student_title  # noqa: F401  (re-exported by sources_ext)

# Job boards and staffing agencies
from .ethosia import src_ethosia
from .dialog import src_dialog
from .nisha import src_nisha
from .gotfriends import src_gotfriends
from .builtin import src_builtin
from .linkedin import src_linkedin
from .cps import src_cps
from .techjob import src_techjob
from .alljobs import src_alljobs

# ATS platforms
from .comeet import src_comeet
from .workday import src_workday
from .lever import src_lever
from .ashby import ASHBY_BOARDS, src_ashby, src_moonactive
from .eightfold import src_eightfold
from .oracle_hcm import src_oracle_hcm
from .smartrecruiters import src_smartrecruiters

# Single-company career sites
from .apple import src_apple
from .camtek import src_camtek
from .qualityai import src_qualityai
from .lemonade import src_lemonade
from .hibob import src_hibob
from .kaltura import src_kaltura
from .google import src_google
from .checkpoint import src_checkpoint
from .meta import src_meta
from .booking import src_booking
from .sap import src_sap
from .pwc import src_pwc

__all__ = [
    "ASHBY_BOARDS",
    "src_ethosia", "src_dialog", "src_nisha", "src_gotfriends", "src_builtin", "src_linkedin",
    "src_cps", "src_techjob", "src_alljobs",
    "src_comeet", "src_workday", "src_lever", "src_ashby", "src_moonactive", "src_eightfold",
    "src_oracle_hcm", "src_smartrecruiters",
    "src_apple", "src_camtek", "src_qualityai", "src_lemonade", "src_hibob", "src_kaltura",
    "src_google", "src_checkpoint", "src_meta", "src_booking", "src_sap", "src_pwc",
]
