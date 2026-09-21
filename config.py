# -*- coding: utf-8 -*-
"""Ron's multi-source Israeli tech-job scanner — configuration & rules."""

# ---- output ----
AUTO_TRACKER = r"C:\Users\User\Desktop\Ron - Job Tracker (AUTO).html"
REGISTRY     = r"D:\jobscan\seen.json"
SUMMARY_DIR  = r"D:\jobscan\daily"

# ---- location rules (drop Jerusalem + South per Ron 2026-09-17) ----
NORTH = {"haifa","krayot","kiryat ata","kiryat bialik","kiryat motzkin","kiryat yam","kiryat haim",
 "yokneam","yoqneam","migdal haemek","migdal ha'emek","karmiel","carmiel","nazareth","natzrat",
 "afula","tiberias","akko","acre","nahariya","nesher","tirat carmel","caesarea","hadera",
 "pardes hanna","zichron","zikhron","sarid","beit shean","bet shean","tefen","migdal tefen",
 "tamra","sakhnin","nof hagalil","kiryat shmona","maalot","shlomi","yavne'el","gush segev"}
SOUTH = {"beer sheva","be'er sheva","beersheba","ashkelon","ashdod","kiryat gat","netivot",
 "sderot","ofakim","dimona","eilat","yeruham","rahat","arad","lehavim","meitar","omer","gedera"}
JERUSALEM = {"jerusalem","yerushalayim","har hotzvim","maale adumim","mevaseret"}
# everything else that is clearly a real city -> Center; unknown -> Unknown (kept, flagged)
DROP_REGIONS = {"South","Jerusalem"}

# ---- referral companies: LOUD flag on good match, quiet 'maybe' on reach ----
REFERRAL_COMPANIES = ["nvidia","philips","camtek","palo alto","paloalto","palo-alto","apple","pwc","pricewaterhouse"]

# ---- giants: always surfaced (scanned via their own ATS too) ----
GIANTS = ["google","meta","facebook","amazon","aws","microsoft","apple","nvidia","intel","mobileye",
 "qualcomm","ibm","cisco","samsung","broadcom","marvell","western digital","sandisk","dell","hp ",
 "hpe","oracle","sap","salesforce","paypal","ebay","booking","wix","monday","checkpoint","check point",
 "nice","cyberark","jfrog","similarweb","taboola","appsflyer","payoneer","fiverr","lightricks","philips","camtek","palo alto"]

# ---- Greenhouse boards (open JSON API) confirmed for Israeli employers ----
GREENHOUSE_SLUGS = ["similarweb","jfrog","melio","payoneer","riskified","taboola","appsflyer",
 "lightricks","fireblocks","gong","wiz","monday"]  # 404s are skipped gracefully

# ---- Comeet public boards (company -> {uid, token}); grows over time (v2) ----
COMEET_BOARDS = {
    # "team8": {"uid": "61.003", "token": "16358C6EF2C61631639B558C0429"},  # example only
}

# ---- lane keywords (his learnable lanes) ----
# STRICT title gate — a role qualifies only if its TITLE contains one of these
# (deliberately NO bare "engineer"/"engineering" — that let in Process/Support/Quality/Mechanical/Flight engineers)
TITLE_DEV = ["developer","software","full stack","fullstack","full-stack","backend","back end","back-end",
 "frontend","front end","front-end",".net","c#","c sharp","c++","python","java","javascript","typescript",
 "node","react","angular","vue","devops","automation","sdet","embedded","firmware","ai engineer",
 "ai developer","ai native","ai-native","llm","genai","data engineer","programmer","validation",
 "מפתח","מפתחת","מתכנת","תוכנה","אוטומציה","הנדסת תוכנה","full-stack"]

# ---- junior / early-career title signals (EN + HE), recognized from the TITLE ----
# These mark a role as junior even when the source gives no level field and the JD
# states no year range. Hebrew apostrophe comes in several code points (' ׳ ’).
JUNIOR_MARK = ["junior","jr.","jr ","entry level","entry-level","entry_level","early career",
 "early-career","new grad","new-grad","new graduate","graduate","grad ","recent graduate",
 "ג'וניור","ג׳וניור","ג’וניור","גוניור","בוגר","בוגרת","משרה התחלתית","תחילת דרך","ללא ניסיון"]

DEV_KEYWORDS = ["developer","develop","software","engineer","engineering","programmer",
 "full stack","fullstack","full-stack","backend","back end","back-end","frontend","front end","front-end",
 ".net","c#","c sharp","python","java ","javascript","typescript","node","react","angular","vue",
 "devops","automation","sdet","qa automation","test automation","embedded","firmware",
 "ai engineer","ai developer","llm","genai","data engineer","integration","validation","verification",
 "מפתח","תוכנה","אוטומציה","הנדסת תוכנה","אינטגרצי"]

# foundation-gap markers -> classify as skip (not learnable on the job)
FOUNDATION_SKIP = ["rtl","vlsi","asic"," uvm","systemverilog","specman"," dft","physical design",
 "analog design"," rf "," dsp ","fpga design","chip design","silicon design","layout",
 "research scientist","phd","algorithm researcher","electro-optic","opto",
 "computer vision","image processing","deep learning research",
 # giant-board noise Ron doesn't want (pull them, but keep them OUT of the tracker):
 "silicon validation","soc validation","system validation"," soc "," soc-","post-silicon",
 "physical verification","dv engineer","design verification",
 # networking / NOS specialization he doesn't have:
 "sonic","networking protocol"," l2 "," l3 ","l2/l3","data plane","control plane"," sai ",
 " nos ","switch asic","routing protocol","bgp","ospf"]

SENIOR_TITLE = ["senior","sr.","sr ","lead","principal","staff","architect","team lead","teamlead",
 "manager","head of","vp ","director","chief","expert","מנהל","בכיר","ראש צוות"]

STUDENT_MARK = ["student","intern","internship","סטודנט","מתמח","משרת סטודנט","הכשרה"]

# ---- CV variants (must match the tracker's CVS list / his files) ----
CV = {
 "ai":"Ron Salama - CV (Software & AI).pdf",
 "backend":"Ron Salama - CV (Backend & Full-Stack).pdf",
 "embedded":"Ron Salama - CV (Firmware & Embedded).pdf",
 "clow":"Ron Salama - CV (C & Low-Level).pdf",
 "test":"Ron Salama - CV (Hardware & Test).pdf",
 "sysint":"Ron Salama - CV (Systems Integration).pdf",
}
