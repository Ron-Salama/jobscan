# -*- coding: utf-8 -*-
"""Regression fixtures for JobScan's keyword rules (audit 2026-09-24).

Every case here is a real role/location/JD snippet that a rule got wrong at some point.
Run:  python -m pytest -q tests/test_rules.py      (or:  python tests/test_rules.py)
No network: only the pure rule functions in jobscan.py / config.py are exercised.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jobscan as J   # noqa: E402
import config as C    # noqa: E402


def _job(title, company="", desc="", level="", source="x", city="Tel Aviv", years_min=None):
    return J.job(source, "1", title, company, city, "https://example/" + title, level,
                 years_min, None, [], desc)


def _lane(title, **kw):
    c = J.classify(_job(title, **kw))
    return None if c is None else (c["lane"], c["why"])


# ---------------- region_of (BUG 10) ----------------
def test_region_hebrew_north():
    assert J.region_of("חיפה והצפון") == "North"
    assert J.region_of("יקנעם") == "North"
    assert J.region_of("כרמיאל") == "North"
    assert J.region_of("קרית אתא") == "North"
    assert J.region_of("North District, Israel") == "North"
    assert J.region_of("Binyamina") == "North"


def test_region_multi_part_any_north_wins():
    assert J.region_of("שפלה, חיפה והצפון, באר שבע והדרום") == "North"
    assert J.region_of("Ramat Gan; Haifa") == "North"


def test_region_south_jerusalem_only_when_every_part_is():
    assert J.region_of("Beer-Sheva") == "South"          # hyphen spelling
    assert J.region_of("באר שבע והדרום") == "South"
    assert J.region_of("ירושלים") == "Jerusalem"
    # agency string listing the South next to the Center is kept (Center)
    assert J.region_of("תל אביב והמרכז, שפלה, באר שבע והדרום") == "Center"


def test_region_whole_token_not_substring():
    assert J.region_of("Homer") == "Center"               # 'omer' (South) inside a word
    assert J.region_of("צפון תל אביב") == "Center"         # 'North Tel Aviv' is not the North
    assert J.region_of("Tel Aviv, Israel") == "Center"
    assert J.region_of("Israel") == "Unknown"
    assert J.region_of("") == "Unknown"


def test_region_abroad_dropped():
    assert J.region_of("Munich, Germany") == "Abroad"
    assert J.region_of("Gurugram, India") == "Abroad"
    assert "Abroad" in C.DROP_REGIONS


# ---------------- parse_years (BUG 11) ----------------
def test_parse_years_up_to_is_a_ceiling():
    assert J.parse_years("Up to 5 years of experience") is None
    assert J.parse_years("עד 3 שנות ניסיון") is None


def test_parse_years_separate_statements_take_max():
    assert J.parse_years("5+ years python ... 1+ years aws") == 5          # Cato 'Field AI Engineer'
    assert J.parse_years("- 5+ years of professional software development experience\n"
                         "- 2+ years of experience in design") == 5         # Amazon Annapurna


def test_parse_years_ranges_decimals_boilerplate():
    assert J.parse_years("0-3 years of experience") == 0
    assert J.parse_years("3-5+ years of experience") == 3
    assert J.parse_years("1.5 years of experience") == 2                  # never read as 5
    assert J.parse_years("מנטור עם 30 שנות ניסיון") is None                # a mentor's boast
    assert J.parse_years("founded 12 years ago. 2 years of experience") == 2
    assert J.parse_years("15+ years since starting the company. 1-2 years of experience") == 1
    assert J.parse_years("no numbers here") is None


def test_parse_years_nice_to_have_is_not_a_requirement():
    assert J.parse_years("1-2 שנות ניסיון בתחום הבדיקות – יתרון") is None
    assert J.parse_years("Requirements: 2+ years of C#\nAdvantages:\n5+ years of Kubernetes") == 2
    assert J.parse_years("6+ years of backend experience using Java (Go is a plus)") == 6
    assert J.parse_years("ניסיון של לפחות 2 שנות פיתוח - דרושה היכרות עם php - עבודה עם debian - יתרון") == 2


# ---------------- student (BUG 9 / REMOVE 7) ----------------
def test_student_title_word_bound():
    assert J.is_student_title("Software Engineering Intern")
    assert J.is_student_title("משרת סטודנט - מפתח/ת")
    assert not J.is_student_title("Runtime Internals Developer")
    assert not J.is_student_title("Internal Tools Engineer")
    assert not J.is_student_title("Graduate Software Engineer")          # graduate = junior


def test_student_level_from_blurb_is_not_trusted():
    # dialog guessed 'student' from the company blurb 'המתמחה בפיתוח' (= 'that specializes in')
    assert _lane("Junior Backend Engineer", company="Dialog", level="student", source="dialog",
                 desc="חברה המתמחה בפיתוח מערכות") == ("apply", "junior")
    # a structured student level (hiremetech/experis/comeet) is still trusted
    assert _lane("Software Developer", level="student", source="experis") == ("skip", "student")


# ---------------- senior (BUG 12) ----------------
def test_senior_word_bound_stems():
    assert not J.is_senior_title("low-level software engineer, platform architecture")
    assert not J.is_senior_title("staffing software developer")
    assert not J.is_senior_title("mvp developer")
    assert J.is_senior_title("software team leader")                    # 'lead' stays a substring
    assert J.is_senior_title("staff software engineer")
    assert J.is_senior_title("software architect")
    assert _lane("Low-level Software Engineer, Platform Architecture", company="Apple",
                 source="apple", desc="2+ years of experience with C/C++") == ("apply", "junior")
    assert _lane("Software Team Leader", company="Foo")[1] == "senior"


# ---------------- title gate (BUG 8) ----------------
def test_title_gate_test_integration_lane():
    for t in ("Integrator", "ATE Development", "SW Engineer", "WiFi FW Engineer", "Test and Product Engineer",
              "Hardware Test Engineer", "מהנדס/ת שילובים – אלת\"א", "מהנדס/ת לתכן מבדקים",
              "Software Verification Engineer", "מהנדס/ת וריפיקציה"):
        assert J.is_dev_title(t.lower()), t


def test_title_gate_short_stems_word_bound():
    assert not J.is_dev_title("pentest product associate")               # 'test product' inside 'pentest'
    assert not J.is_dev_title("private equity associate")                # 'ate' inside a word
    assert not J.is_dev_title("junior verification engineer")            # bare 'verification' not added


# ---------------- manual QA (BUG 13) ----------------
def test_manual_qa_exemptions():
    assert not J.is_manual_qa("בודק/ת אוטומציה לחברת סליקה")
    assert not J.is_manual_qa("qa ידני ואוטומציה")
    assert not J.is_manual_qa("software qa engineer",
                              "Develop and maintain automation frameworks; C#, Python, Pytest")
    assert J.is_manual_qa("software qa engineer", "Run test plans and report bugs")
    assert J.is_manual_qa("דרוש/ה manual sw tester | אלביט")


# ---------------- foundation / industrial (ADD 4, ADD 6) ----------------
def test_dv_and_plc_are_skipped():
    assert _lane("Pre-Silicon Validation Engineer", company="NVIDIA")[1] == "foundation-gap"
    assert _lane("Software Verification Engineer", level="junior",
                 desc="UVM testbench, SystemVerilog, RTL")[1] == "foundation-gap"
    assert _lane("Software Verification Engineer", level="junior",
                 desc="C# test tools for system V&V") == ("apply", "junior")
    assert _lane("מהנדס/ת בקרה ואוטומציה", level="junior", source="hiremetech")[1] == "industrial-control"


# ---------------- company matching (GIANTS / REFERRAL) ----------------
def test_company_is_word_bound():
    for co in ("HP", "HP Inc", "HPE", "Palo Alto Networks", "Check Point", "SanDisk", "Mobileye",
               "NICE", "Qualcomm", "Cisco"):
        assert J.company_is(co, C.GIANTS), co
    assert J.company_is("Palo Alto Networks", C.REFERRAL_COMPANIES)
    assert J.company_is("PwC NEXT", C.REFERRAL_COMPANIES)          # the referral is PwC NEXT only (call #13)
    for co in ("Sapiens", "Metalab", "Intelligo", "Applied Materials", "(masked)", ""):
        assert not J.company_is(co, C.GIANTS), co


# ---------------- dedup / norm (BUG 2) ----------------
def test_norm_keeps_language_identity():
    assert J.norm("C# Developer") != J.norm("C Developer")
    assert J.norm("C++ Developer") != J.norm("C Developer")
    assert J.norm(".NET Developer") != J.norm("NET Developer")


def test_masked_rows_never_merged_on_title():
    a = J.normalize(_job("Junior Software Engineer", source="hiremetech", desc="Bellboy Robotics " * 20))
    b = J.normalize(_job("Junior Software Engineer", source="hiremetech", desc="Medtronic is a global " * 20))
    b["sid"] = "2"
    assert len(J.dedup([a, b])) == 2
    assert J.soft_key(a) != J.soft_key(b)                               # JD fingerprint differs
    assert J.soft_key(J.normalize(_job("Junior Software Engineer", desc="short"))) is None


def test_named_rows_merge_across_sources_only():
    a = J.normalize(_job("Backend Developer", company="Wix", source="linkedin"))
    b = J.normalize(_job("Backend Developer", company="Wix", source="builtin"))
    c = J.normalize(_job("Backend Developer", company="Wix", source="builtin")); c["sid"] = "9"
    out = J.dedup([a, b, c])
    assert len(out) == 2 and out[0]["_sources"] == {"linkedin", "builtin"}


def test_soft_key_suppression_goes_to_bucket():
    reg = {"seen": {}}
    first = J.normalize(_job("Junior Full Stack Engineer", source="hiremetech", city="Lod",
                             desc="0-2 years full stack, React, Node, Lod office " * 5, level="junior"))
    assert len(J.select([first], reg)) == 1
    repost = dict(first); repost["sid"] = "2"; repost["url"] = "https://example/repost"
    bucket = []
    assert J.select([J.normalize(repost)], reg, bucket) == []
    assert [b["reason"].split(":")[0] for b in bucket] == ["dup-suppressed"]


# ---------------- CV pick (CHANGE 1) ----------------
def test_cv_from_title_first():
    assert J.pick_cv("Junior QA Automation Engineer", "adopting ai tooling, latest stack") == C.CV["test"]
    assert J.pick_cv("Junior Unreal Engine Developer", "C++ Unreal") == C.CV["gametech"]
    assert J.pick_cv("Firmware Engineer") == C.CV["embedded"]
    assert J.pick_cv("Agentic AI Engineer") == C.CV["ai"]
    assert J.pick_cv("Junior Full Stack Developer") == C.CV["backend"]
    assert J.pick_cv("Junior C Developer") == C.CV["clow"]
    assert J.pick_cv("Software Engineer", "backend, REST API, microservices, SQL") == C.CV["backend"]
    assert J.pick_cv("Software Engineer") == C.CV["general"]
    assert "sysint" not in C.CV


# ---------------- misc (ADD 3, CHANGE 3) ----------------
def test_no_jd_title_bucket():
    bucket = []
    row = J.normalize(_job("מהנדס/ת מערכת", source="experis", desc="נדרש ניסיון משרה מלאה"))
    J.select([row], {"seen": {}}, bucket)
    assert [b["reason"] for b in bucket] == ["no-jd-title"]


def test_today_is_iso_date():
    assert len(J.TODAY) == 10 and J.TODAY[4] == "-" and J.TODAY[7] == "-"


# ---------------- code-review fixes (2026-09-24) ----------------
def test_review_title_gate_s_w_word_bound():
    assert not J.is_dev_title("sales/web analyst")                     # 's/w' inside 'sales/web'
    assert not J.is_dev_title("operations/warehouse coordinator")
    for t in ("S/W Engineer", "HW/SW Integrator", "SW/FW Engineer", "מהנדס/ת מבדקים"):
        assert J.is_dev_title(t.lower()), t
    assert not J.is_dev_title("מבדקים רפואיים")                          # bare 'מבדקים' dropped


def test_review_not_sw_test_titles_skipped():
    for t in ("Mechanical Test Engineer", "Penetration Tester Automation", "Pentest Automation Engineer"):
        assert _lane(t, level="junior") == ("skip", "not-sw-test"), t
    assert _lane("Junior Test Engineer", level="junior") == ("apply", "junior")


def test_review_dv_needs_unambiguous_marker():
    assert _lane("Software Verification Engineer", level="junior",
                 desc="Work next to the RTL team on C# test tools") == ("apply", "junior")
    assert _lane("Software Verification Engineer", level="junior",
                 desc="Python tools for ASIC bring-up") == ("apply", "junior")
    assert _lane("Software Verification Engineer", level="junior",
                 desc="SystemVerilog testbenches")[1] == "foundation-gap"


def test_review_company_glued_slug_needs_suffix():
    assert not J.company_is("Bookingjini", ["booking"])
    assert J.company_is("Booking.com", ["booking"])
    assert not J.company_is("Marvellous Ltd", ["marvell"])
    assert J.company_is("Marvell Israel", ["marvell"])
    assert J.company_is("PaloAltoNetworks", C.REFERRAL_COMPANIES)
    assert J.company_is("nvidiaisrael", C.GIANTS)


def test_review_parse_years_company_history_and_own_statement():
    assert J.parse_years("The company has been operating for 12 years. 1-2 years of experience") == 1
    assert J.parse_years("12 years of growth. 2 years of experience") == 2
    # another bullet's '- advantage' must not attach to a real requirement (flattened JD)
    assert J.parse_years("Docker - advantage - 3+ years of Python experience") == 3
    assert J.parse_years("3+ years of hands-on experience developing backend services in Python"
                         " - familiarity with AWS, an advantage") == 3
    assert J.parse_years("3 years - a plus") is None                    # short statement + its marker


def test_review_soft_key_same_source_other_city_is_a_new_req():
    reg = {"seen": {}}
    haifa = J.normalize(_job("Junior Backend Engineer", company="Foo", source="linkedin", city="Haifa",
                             level="junior"))
    assert len(J.select([haifa], reg)) == 1
    yok = dict(haifa, sid="2", url="https://example/yokneam", city="Yokneam")
    assert len(J.select([J.normalize(yok)], reg)) == 1                  # same source, other city: admitted
    other = dict(haifa, sid="3", url="https://example/other", city="Nesher", source="builtin")
    bucket = []
    assert J.select([J.normalize(other)], reg, bucket) == []            # another board's copy: suppressed
    assert bucket[0]["reason"].startswith("dup-suppressed")


def test_review_failed_run_queues_overflow_referral_first():
    import tempfile, types
    fake = types.ModuleType("notify")
    fail_n = {"n": 10}
    def notify_jobs(rows, failed=None):
        n = fail_n["n"]; failed.extend(rows[len(rows) - n:]); return len(rows) - n  # the last n roles fail
    fake.notify_jobs = notify_jobs; fake.notify_text = lambda t: False
    saved = {k: os.environ.pop(k, None) for k in ("JOBSCAN_NO_ALERT", "GITHUB_ACTIONS")}
    last_reg = dict(J._LAST_REG)
    old = sys.modules.get("notify"); sys.modules["notify"] = fake
    try:
        def row(i, ref=False):
            return {"company": "Co%d" % i, "role": "Dev", "region": "North", "url": "https://x/%d" % i,
                    "cv": "", "openings": {"note": ("REFERRAL " if ref else "") + "GIANT ALERT"}}
        # 64 roles -> 60 sent (the referral role first) + 4 overflow
        rows = [row(i) for i in range(J.ALERT_BATCH_MAX + 3)] + [row(900, True)]
        with tempfile.TemporaryDirectory() as d:
            reg = {"seen": {}}
            J.send_alerts(rows, reg, os.path.join(d, "seen.json"))       # last message (10 roles) fails
            q = [it["url"] for it in reg["alert_queue"]]
            assert len(q) == 14 and "https://x/%d" % (J.ALERT_BATCH_MAX + 2) in q   # 10 failed + 4 overflow
            assert reg["alert_fail_streak"] == 1
            fail_n["n"] = J.ALERT_BATCH_MAX; reg = {"seen": {}}
            J.send_alerts(rows, reg, os.path.join(d, "seen.json"))       # everything fails: 64 > queue cap
            q = [it["url"] for it in reg["alert_queue"]]
            assert len(q) == J.ALERT_QUEUE_MAX and q[0] == "https://x/900"   # head kept: referral first
            fail_n["n"] = 0; reg = {"seen": {}}
            J.send_alerts(rows, reg, os.path.join(d, "seen.json"))       # delivered: overflow not queued
            assert reg["alert_queue"] == [] and reg["alert_fail_streak"] == 0
    finally:
        if old is not None: sys.modules["notify"] = old
        else: sys.modules.pop("notify", None)
        for k, v in saved.items():
            if v is not None: os.environ[k] = v
        J._LAST_REG.clear(); J._LAST_REG.update(last_reg)


def test_review_notify_drops_rejected_single_role_only():
    import notify
    orig = (notify._send, notify.configured)
    notify._send = lambda text: None; notify.configured = lambda: True     # channel rejects every message
    try:
        failed = []
        assert notify.notify_jobs([{"company": "A", "role": "Dev", "url": "u1"}], failed) == 0
        assert failed == []                                              # single role: dropped, not queued
        two = [{"company": "A", "role": "Dev", "url": "u1"}, {"company": "B", "role": "Dev", "url": "u2"}]
        assert notify.notify_jobs(two, failed) == 0 and len(failed) == 2  # a batch stays retryable
    finally:
        notify._send, notify.configured = orig
    assert notify._cv_label("Ron_Salama_CV") == "General"
    assert notify._cv_label("Hardware_Test_Integration") == "Hardware_Test_Integration"


def test_review_cloud_run_helpers():
    import cloud_run as CR
    v, _ = CR._norm_map({"https://a/1": {"v": "YES"}, "https://a/1/": {"v": "NO"}}, CR._VRANK_VERDICTS)
    assert v["https://a/1"]["v"] == "NO"                                 # a NO tombstone wins
    v, _ = CR._norm_map({"https://a/1": {"v": "YES"}, "https://a/1/": {"v": "NO"}})
    assert v["https://a/1"]["v"] == "YES"                                # jobify/rescued: YES>REACH>NO
    assert CR._rkey("dup-suppressed: https://x/y") == "dup-suppressed"
    assert CR._review_key({"role": "Undergraduate student developer", "reason": "review:x"})[0] == 1
    assert CR._review_key({"role": "Graduate developer", "reason": "review:x"})[0] == 0
    for u in ("https://lnkd.in/abc", "https://wa.me/972500", "https://app.hibob.com/x", "https://sqlink.com/j/1"):
        assert CR._company_from_host(u) == "", u
    assert CR._company_from_host("https://app.rafael.co.il/x") == "Rafael"
    assert CR._entry_region({"loc": "", "role": "Developer (Beer Sheva)", "region": "Center"}) == ("South", "South")
    assert CR._entry_region({"loc": "", "role": "Software Engineer", "region": ""})[1] == ""


def test_review_source_alert_once_per_issue_per_day():
    import types
    import cloud_run as CR
    sent = []
    fake = types.ModuleType("notify"); fake.notify_text = lambda msg: sent.append(msg) or True
    saved = os.environ.pop("JOBSCAN_NO_ALERT", None)
    old = sys.modules.get("notify"); sys.modules["notify"] = fake
    try:
        reg = {"source_stats": {"alpha": {"max": 50}, "beta": {"max": 40}}}
        CR.check_sources_dark(reg, {"alpha": 0, "beta": 40})
        CR.check_sources_dark(reg, {"alpha": 0, "beta": 40})             # same issue, same day: not re-sent
        assert len(sent) == 1 and "alpha" in sent[0]
        CR.check_sources_dark(reg, {"alpha": 0, "beta": 0})              # a NEW issue the same day: sent
        assert len(sent) == 2 and "beta" in sent[1] and "alpha" not in sent[1]
    finally:
        if old is not None: sys.modules["notify"] = old
        else: sys.modules.pop("notify", None)
        if saved is not None: os.environ["JOBSCAN_NO_ALERT"] = saved


def test_followup_test_development_titles_pass_gate():
    for t in ("מהנדס/ת פיתוח מבדקים", "מהנדס מבדקים", "מהנדסת מבדקים", "מהנדס/ת לתכן מבדקים"):
        assert J.is_dev_title(t.lower()), t


def test_followup_editor_final_kaf_skipped():
    assert J.is_not_sw_test("עורך/ת וידאו ומפתח/ת")
    assert J.is_not_sw_test("עורכת תוכן")
    assert not J.is_not_sw_test("test automation engineer")


def test_followup_years_in_the_industry_counts():
    assert J.parse_years("5+ years in the industry") == 5
    assert J.parse_years("The company has been operating for 12 years. 1-2 years of experience") == 1


def test_followup_galilee_places_are_north():
    for loc in ("Galil Tachton (North)", "Tel Hai", "Ein Harod", "גליל עליון", "קצרין"):
        assert J.region_of(loc) == "North", loc
    assert J.region_of("Gelil Yam, Herzliya") == "Center"


# ---------------- Ron's judgment calls, 2026-09-24 ----------------
def test_call1_verification_software_titles_pass_gate():
    for t in ("Verification Software Engineer", "SW Verification Engineer", "V&V Engineer",
              "Software Verification & Validation Engineer", "Firmware Verification Engineer",
              "System Integration & Verification Engineer", "BSP and BMC Verification Software Engineer"):
        assert J.is_dev_title(t.lower()), t
    assert not J.is_dev_title("verification engineer")              # bare = chip DV risk, not gated in
    assert _lane("Design Verification Engineer") is None               # chip DV: never gated in
    assert _lane("Design Verification Software Engineer")[1] == "foundation-gap"


def test_call7_devops_ml_reach_unless_pure_junior():
    assert _lane("DevOps Engineer", desc="1-3 years of experience with AWS") == ("reach", "profile-gap")
    assert _lane("ML Engineer", desc="2+ years building models") == ("reach", "profile-gap")
    assert _lane("Junior DevOps Engineer") == ("apply", "junior-learn-on-job")       # no years = learn on the job
    assert _lane("DevOps Engineer", desc="0-2 years of experience") == ("apply", "junior-learn-on-job")
    assert _lane("Junior DevOps Engineer", desc="2+ years of experience") == ("reach", "profile-gap")
    assert _lane("Senior DevOps Engineer")[0] == "skip"
    # not profile-gap: AI app engineering, cloud *software*, platform
    assert _lane("Junior AI Engineer") == ("apply", "junior")
    assert _lane("Junior Cloud Software Engineer") == ("apply", "junior")
    c = J.classify(_job("DevOps Engineer", company="NVIDIA"))
    assert (c["lane"], c["why"], c["tailor"]) == ("reach", "profile-gap", False)       # no giant ping


def test_call8_experienced_title_is_reach():
    assert _lane("Experienced Backend Developer") == ("reach", "experienced-title")
    assert _lane("Experienced Backend Developer", desc="1-3 years of experience") == ("reach", "experienced-title")
    assert _lane("מפתח/ת Full Stack מנוסה") == ("reach", "experienced-title")
    assert _lane("Experienced Backend Developer", desc="5+ years of experience")[0] == "skip"
    assert _lane("Senior Experienced Developer")[0] == "skip"


def test_call9_junior_title_with_4y_goes_to_review():
    assert _lane("Junior Software Engineer", desc="4+ years of experience in C++") == ("review", "junior-title-vs-years")
    c = J.classify(_job("Junior Software Engineer", company="NVIDIA", desc="5+ years of experience"))
    assert (c["lane"], c["why"]) == ("review", "junior-title-vs-years")
    assert _lane("Junior Software Engineer", desc="1-2 years of experience") == ("apply", "junior")


def test_call13_referral_is_pwc_next_not_all_pwc():
    for co in ("PwC NEXT", "PwC | NEXT Technology Solutions"):
        assert J.company_is(co, C.REFERRAL_COMPANIES), co
    for co in ("PwC Israel", "PricewaterhouseCoopers", "Next Insurance", "NextSilicon"):
        assert not J.company_is(co, C.REFERRAL_COMPANIES), co
    assert not J.ref_digest_ok("penetration tester - jb-727")          # pentest is not his lane


def test_review_experienced_giant_keeps_ping():
    for d in ("Requirements: 2+ years of experience in C++ and Linux-free test tools for our lab.",
              "We build C++ test tools for our lab systems; strong OOP and debugging skills are needed.",
              "Requirements: 3+ years of experience in C++ and test tools for our lab systems."):
        c = J.classify(_job("Experienced Software Engineer", company="NVIDIA", desc=d))
        assert (c["lane"], c["why"], c["tailor"]) == ("reach", "experienced-title", True), d
    c = J.classify(_job("Experienced DevOps Engineer", company="Mobileye", desc="2+ years of experience with AWS and CI tooling."))
    assert (c["lane"], c["why"], c["tailor"]) == ("reach", "profile-gap", False)   # #7 stays ping-free


def test_review_vv_title_gets_dv_guard():
    assert _lane("Junior V&V Engineer", desc="Build UVM / SystemVerilog testbenches for ASIC blocks")[1] == "foundation-gap"
    assert _lane("Junior V&V Engineer", desc="Develop C# and Python test tools for system V&V") == ("apply", "junior")


def test_review_profile_gap_uses_title_head_and_hebrew():
    assert not J.is_profile_gap_title("software engineer, devops tools")
    assert not J.is_profile_gap_title("python developer - sre team")
    assert J.is_profile_gap_title("backend & devops engineer")
    assert J.is_profile_gap_title("מהנדס/ת לצוות הdevops")
    assert J.is_experienced_title("מפתח/ת full stack מנוס/ה") and J.is_experienced_title("המנוסה")
    assert not J.is_experienced_title("inexperienced") and not J.is_experienced_title("מנוסח")


def test_review_region_placeholders_and_spellings():
    for l in ("Location not specified", "Israel - 2 Locations", "2+ Locations", "3 מיקומים", "Various locations"):
        assert J.region_of(l) == "Unknown", l
    for l in ("Bergisch Gladbach", "Rösrath"):
        assert J.region_of(l) == "Abroad", l
    for l in ("Yizre'el", "קיבוץ יזרעאל", "Yokne'am Illit", "Kiryat Shemona, Israel"):
        assert J.region_of(l) == "North", l


def test_review_digest_role_filter():
    for t in ("business development representative", "talent development specialist", "engineering program coordinator",
              "מהנדס/ת חומרה", "מהנדס/ת בדיקות לחומרה", "physical layer architecture engineer",
              "interconnect hardware characterization engineer", "electrical engineer"):
        assert not J.ref_digest_ok(t), t
    for t in ("nvlink qa engineer", "network solution verification engineer", "technical product engineer (cortex)",
              "system engineer"):
        assert J.ref_digest_ok(t), t
    assert J.digest_title_key("PANW", "QA Engineer (Cortex XDR)") != J.digest_title_key("PANW", "QA Engineer (Prisma Cloud)")
    assert J.digest_title_key("X", "C# Developer") != J.digest_title_key("X", "C++ Developer")


def test_review_digest_unknown_copy_and_length_budget():
    os.environ.pop("JOBSCAN_NO_ALERT", None)
    import notify
    sent = []
    orig = (notify.configured, notify._send)
    notify.configured = lambda: True
    notify._send = lambda text: sent.append(text) or (len(text) <= 4096 or None)
    try:
        reg = {"seen": {}}
        wd = {"url": "wd", "company": "NVIDIA", "role": "Nvlink QA Engineer", "region": "North"}
        bi = {"url": "bi", "company": "NVIDIA", "role": "Nvlink QA Engineer", "region": "Unknown"}   # '2 Locations'
        ta = {"url": "li", "company": "NVIDIA", "role": "Nvlink QA Engineer", "region": "Center"}    # another site
        assert J.send_ref_digest([bi, wd, ta], reg) == 2 and "[Unknown]" not in sent[-1]
        long = [{"url": "https://x.example/" + "p" * 380 + str(i), "company": "Palo Alto Networks (CyberArk)",
                 "role": "QA Automation Engineer %02d " % i + "x" * 50, "region": "Center"} for i in range(12)]
        n = J.send_ref_digest(long, reg)
        assert 0 < n < 12 and len(sent[-1]) <= 4096 and "more in the next run" in sent[-1]
        assert J.send_ref_digest(long, reg) == 12 - n or len(sent[-1]) <= 4096
    finally:
        notify.configured, notify._send = orig


def _raw(title, company, url, city="Yokneam"):
    j = _job(title, company=company, city=city)
    j["url"] = url; j["region"] = J.region_of(city)
    return j


def test_call10_referral_digest_collects_gate_misses():
    raw = [_raw("Nvlink QA Engineer", "NVIDIA", "u1"),                  # misses the gate, relevant -> digest
           _raw("Hardware Test Engineer", "NVIDIA", "u2"),               # passes the gate -> tracker, not digest
           _raw("Senior Networking QA Engineer", "NVIDIA", "u3"),        # senior -> not digest
           _raw("Account Manager", "NVIDIA", "u4"),                      # non-dev -> not digest
           _raw("ASIC Design Engineer", "NVIDIA", "u5"),                 # chip design -> not digest
           _raw("Nvlink QA Engineer", "SomeStartup", "u6")]              # not a referral company
    dig = []
    J.select(raw, {"seen": {}}, [], [], [], dig)
    assert [d["url"] for d in dig] == ["u1"]


def test_call10_referral_digest_new_only_dedup_rollover():
    os.environ.pop("JOBSCAN_NO_ALERT", None)
    import notify
    sent = []
    orig = (notify.configured, notify._send)
    notify.configured = lambda: True
    notify._send = lambda text: sent.append(text) or True
    try:
        reg = {"seen": {}}
        a = {"url": "u1", "company": "NVIDIA", "role": "Nvlink QA Engineer", "region": "North"}
        a2 = {"url": "li-copy", "company": "NVIDIA", "role": "Nvlink QA Engineer", "region": "North"}
        b = {"url": "u2", "company": "NVIDIA", "role": "Cloud QA Engineer", "region": "Center"}
        assert J.send_ref_digest([a, a2], reg) == 1                   # the LinkedIn copy is the same role
        assert J.send_ref_digest([a, a2, b], reg) == 1                # only the NEW one goes out
        assert len(sent) == 2 and "Cloud QA Engineer" in sent[1] and "Nvlink" not in sent[1]
        assert J.send_ref_digest([a, b], reg) == 0 and len(sent) == 2  # nothing new -> no message
        many = [{"url": "m%d" % i, "company": "Camtek", "role": "System Engineer %d" % i, "region": "North"}
                for i in range(J.REF_DIGEST_MAX + 3)]
        assert J.send_ref_digest(many, reg) == J.REF_DIGEST_MAX and "+3 more" in sent[-1]
        assert J.send_ref_digest(many, reg) == 3                      # the rest roll to the next run
        notify._send = lambda text: False                               # failed delivery -> retried later
        c = {"url": "u3", "company": "NVIDIA", "role": "QA Engineer", "region": "North"}
        assert J.send_ref_digest([c], reg) == 0 and "u3" not in reg["ref_digest"]
    finally:
        notify.configured, notify._send = orig


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("ok  ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, type(e).__name__, e)
    print("%d failed" % fails)
    sys.exit(1 if fails else 0)
