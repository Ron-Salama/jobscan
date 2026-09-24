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
    assert J.region_of("קרית אתא") == "North"          # Ron's home town
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
    assert J.company_is("PricewaterhouseCoopers", C.REFERRAL_COMPANIES)
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
