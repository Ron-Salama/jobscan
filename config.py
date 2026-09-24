# -*- coding: utf-8 -*-
"""Ron's multi-source Israeli tech-job scanner — configuration & rules."""

# ---- output ----
AUTO_TRACKER = r"C:\Users\User\Desktop\Ron - Job Tracker (AUTO).html"
REGISTRY     = r"D:\jobscan\seen.json"
SUMMARY_DIR  = r"D:\jobscan\daily"

# ---- location rules (drop Jerusalem + South per Ron 2026-09-17) ----
# Matched by jobscan.region_of() as WHOLE tokens (English: word-bound; Hebrew: letter-bound,
# allowing the one/two-letter prefixes ו/ה/ב/ל/מ/ש/כ), after splitting the location on , / | ;
# so short names like 'עכו' / 'arad' / 'omer' never match inside other words.
NORTH = {"haifa","krayot","kiryat ata","kiryat bialik","kiryat motzkin","kiryat yam","kiryat haim",
 "yokneam","yoqneam","migdal haemek","migdal ha'emek","karmiel","carmiel","nazareth","natzrat",
 "afula","tiberias","akko","acre","nahariya","nesher","tirat carmel","caesarea","hadera",
 "pardes hanna","zichron","zikhron","sarid","beit shean","bet shean","tefen","migdal tefen",
 "tamra","sakhnin","nof hagalil","kiryat shmona","maalot","shlomi","yavne'el","gush segev",
 # added 2026-09-24 (audit BUG 10): places + district names that fell through to Center
 "misgav","binyamina","or akiva","rosh pina","rosh pinna","tivon","kiryat tivon","safed","tzfat",
 "zefat","north district","northern district","northern","haifa district","galilee","atlit",
 # Hebrew (every Hebrew location used to become Center)
 "חיפה","הצפון","מחוז הצפון","מחוז צפון","קריות","הקריות","קרית אתא","קריית אתא","ביאליק",
 "קרית ביאליק","קריית ביאליק","מוצקין","קרית מוצקין","קריית מוצקין","קרית ים","קריית ים",
 "קרית חיים","קריית חיים","יקנעם","יוקנעם","כרמיאל","נשר","טירת כרמל","טירת הכרמל","עכו",
 "נהריה","מגדל העמק","עפולה","נצרת","נוף הגליל","טבריה","תפן","מגדל תפן","משגב","קיסריה",
 "חדרה","זכרון יעקב","זיכרון יעקב","בנימינה","אור עקיבא","ראש פינה","צפת","טבעון",
 "קרית טבעון","קריית טבעון","קרית שמונה","קריית שמונה","מעלות","שלומי","בית שאן","סחנין",
 "טמרה","פרדס חנה","הגליל","עמק יזרעאל","חוף הכרמל","עתלית"}
# (deliberately NOT bare 'צפון'/'דרום'/'גליל': 'צפון תל אביב', 'דרום תל אביב', 'גליל ים' are Center)
SOUTH = {"beer sheva","be'er sheva","beer-sheva","be'er-sheva","beersheba","ashkelon","ashdod",
 "kiryat gat","netivot","sderot","ofakim","dimona","eilat","yeruham","rahat","arad","lehavim",
 "meitar","omer","gedera","south district","southern district","negev",
 "באר שבע","באר-שבע","הדרום","מחוז הדרום","מחוז דרום","אשדוד","אשקלון","קרית גת","קריית גת",
 "דימונה","אילת","נתיבות","שדרות","אופקים","ירוחם","רהט","ערד","להבים","מיתר","הנגב"}
JERUSALEM = {"jerusalem","yerushalayim","har hotzvim","maale adumim","ma'ale adumim","mevaseret",
 "beit shemesh","bet shemesh","jerusalem district",
 "ירושלים","מבשרת","מבשרת ציון","מעלה אדומים","בית שמש","הר חוצבים"}
# Clearly outside Israel (builtin/LinkedIn/giant boards leak these) -> dropped.
ABROAD = {"germany","munich","berlin","frankfurt","india","gurugram","gurgaon","bangalore",
 "bengaluru","hyderabad","pune","chennai","noida","usa","united states","new york","san francisco",
 "california","seattle","austin","boston","chicago","london","united kingdom","uk","england",
 "poland","warsaw","krakow","ukraine","kyiv","kiev","romania","bucharest","cyprus","limassol",
 "portugal","lisbon","spain","madrid","barcelona","france","paris","netherlands","amsterdam",
 "canada","toronto","singapore","japan","tokyo","china","shanghai","australia","sydney",
 "ireland","dublin","serbia","belgrade","bulgaria","sofia","czech republic","prague","hungary",
 "budapest","switzerland","zurich","austria","vienna","sweden","stockholm","taiwan","korea",
 "seoul","vietnam","philippines","mexico","brazil","argentina"}
# location strings that only say "Israel" (or "anywhere") carry no region -> Unknown
REGION_GENERIC = {"israel","ישראל","il","isr","כל הארץ","all israel","multiple locations"}
# everything else that is clearly a real city -> Center; unknown -> Unknown (kept, flagged)
DROP_REGIONS = {"South","Jerusalem","Abroad"}

# Both company lists below are matched by jobscan.company_is() as WHOLE words of the company
# name (never raw substrings: 'sap' must not hit 'Sapiens', 'meta' not 'Metalab', 'intel' not
# 'Intelligo'); names of 6+ letters also match a glued slug when the rest is only a corporate
# suffix ('paloaltonetworks', 'nvidiaisrael' - but not 'Bookingjini' / 'Marvellous').
# ---- referral companies: LOUD flag on good match, quiet 'maybe' on reach ----
REFERRAL_COMPANIES = ["nvidia","philips","camtek","palo alto","paloalto","palo-alto","apple","pwc","pricewaterhouse",
 "pricewaterhousecoopers"]

# ---- giants: always surfaced (scanned via their own ATS too) ----
GIANTS = ["google","meta","facebook","amazon","aws","microsoft","apple","nvidia","intel","mobileye",
 "qualcomm","ibm","cisco","samsung","broadcom","marvell","western digital","sandisk","dell","hp",
 "hpe","hewlett packard","oracle","sap","salesforce","paypal","ebay","booking","wix","monday","checkpoint","check point",
 "nice","cyberark","jfrog","similarweb","taboola","appsflyer","payoneer","fiverr","lightricks","philips","camtek","palo alto"]

# ---- Greenhouse boards (open JSON API) confirmed for Israeli employers ----
# 2026-09-24: 'gong'/'wiz' 404 -> live boards are 'gongio'/'wizinc'; 'monday' 404 (moved to Ashby).
GREENHOUSE_SLUGS = ["similarweb","jfrog","melio","payoneer","riskified","taboola","appsflyer",
 "lightricks","fireblocks","gongio","wizinc",
 # added 2026-09-23 (probed live, confirmed Israel jobs):
 "catonetworks","transmitsecurity","axonius","forter","yotpo","orcasecurity","augury",
 "island","lightrun","descope",
 # added 2026-09-23 (board-discovery, confirmed Israel jobs):
 "bringg","tipaltisolutions","nextinsurance66","atbayjobs","aidocmedical","playtikaltd"]  # a 404 is logged + counted, then skipped
# display name for slugs that aren't the company's name (only for boards added after rows existed,
# so existing company|title dedup keys don't change)
GREENHOUSE_NAMES = {"gongio":"Gong","wizinc":"Wiz"}

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
 "מפתח","מפתחת","מתכנת","תוכנה","אוטומציה","הנדסת תוכנה","full-stack",
 # added 2026-09-22 from real dropped-role analysis:
 "prompt engineer","ml engineer","machine learning engineer","sre","site reliability",
 "sdk","react native","platform engineer","cloud engineer","integration engineer","data platform",
 "mobile developer","founding engineer","software architect",
 # added 2026-09-24 (audit BUG 8): Ron's core test / integration / SW-FW lane had no terms.
 # (deliberately NOT bare 'integration'/'integrat' -> 'Technical Support & Integrations Engineer';
 #  NOT bare 'verification' (chip DV) or 'linux' (sysadmin) -> Ron's judgment calls)
 "integrator","system integration","hw/sw","mlops",
 "labview","teststand","software verification","system verification","sw verification",
 # (not bare 'מבדקים' = 'tests/exams' in any field; review 2026-09-24)
 "אינטגרציה","אינטגרטור","שילובים","ולידציה","ואלידציה","תכן מבדקים","מהנדס/ת מבדקים",
 'צב"ד',"צב״ד","וריפיקציה"]
# Title terms checked WORD-BOUND (jobscan._has_word): as substrings 'sw' hits 'swift'/'switch',
# 'ate' hits 'private'/'state', 's/w' hits 'Sales/Web' / 'Operations/Warehouse', and
# 'test engineer'/'test product' hit 'Pentest Engineer'/'Pentest Product'.
TITLE_DEV_WORDS = ["sw","fw","ate","s/w",
 "test engineer","test engineering","testing engineer","test product","test and product",
 "test equipment","test system","test systems","development in test","test development"]

# JD-content safety net: if a TITLE misses TITLE_DEV but the JD contains this many of these
# programming/framework signals, the role is put in the REVIEW BUCKET (not dropped, not on the
# tracker) so Claude can catch oddly-titled/typo'd/Hebrew dev roles by content, not just title.
DEVSIG = ["python","java","c++","c#","c sharp",".net","javascript","typescript","react","node.js",
 "node ","angular","vue","backend","back-end","back end","frontend","front-end","full stack","fullstack",
 "rest api","restful","microservice","sql","nosql","docker","kubernetes","linux","ci/cd","embedded",
 "firmware","oop","object-oriented","spring","django","flask","golang"," go ","kotlin","git ","גיט",
 "שפת תכנות","פיתוח תוכנה","אלגוריתמ","כתיבת קוד","מיקרו-שירות","ווב",
 # added 2026-09-24 (audit ADD 5): Ron's ATE / instrument-control / test-tool vocabulary.
 # Only feeds the jd-signal bucket rescue, never the tracker.
 "labview","teststand","scpi","gpib","visa ","modbus","rs232","rs-232","wpf","winforms",
 "multithread","instrument"]
DEVSIG_MIN = 3
# but never rescue these clearly-non-dev titles even if their JD name-drops tools:
# (student/intern titles are excluded via jobscan.is_student_title - word-bound, so that
#  'internal'/'international' no longer block a rescue)
DEVSIG_NONDEV = ["analyst","manager","support","sales","marketing","recruit","hr ",
 "mechanical","chemical","physicist","physics","biolog","account","finance","operations","logistics",
 "procurement","customer success","teacher","technician","pre-sale","presale","field engineer",
 "process engineer","quality engineer","application engineer","mechanic","optic","pcb"," rf ",
 "network administrator","noc","help desk","helpdesk","tier 1","system administrator","sysadmin",
 # Hebrew non-dev engineering / business titles (Experis/AllJobs/Drushim)
 "מכונות","מכני","כימי","אזרחי","בניין","תעשייה וניהול","ייצור","תהליכים","רכש","לוגיסטיקה",
 "מכירות","שיווק","גיוס","כספים","חשבונ","טכנאי","איכות","חומרים","אווירו",
 "מהנדס/ת ביצוע ","מהנדס ביצוע ",   # site/construction engineer (trailing space: not 'ביצועים' = performance)
 "שירות שטח","field service","manufacturing","board design"]

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
 "physical verification","dv engineer","design verification","serdes","serializer","deserializer",
 "hw serdes","spiv","phy layer",
 # networking / NOS specialization he doesn't have:
 "sonic","networking protocol"," l2 "," l3 ","l2/l3","data plane","control plane"," sai ",
 " nos ","switch asic","routing protocol","bgp","ospf",
 # added 2026-09-24 (audit ADD 4): chip-DV / silicon terms, needed before any 'verification'
 # title term (classify() checks this list word-bound, so short 'rtl'/'asic'/'uvm' are safe)
 "pre-silicon","pre silicon","presilicon","post silicon","formal verification","cpu verification",
 "digital verification","emulation verification","uvm","verilog","vhdl"]
# JD words that mark a *verification* title as chip DV (checked only for verification titles).
# Unambiguous DV markers only: 'rtl' / 'asic' / 'pre-silicon' also appear in the JDs of the
# software/system V&V roles that sit next to chip teams (review 2026-09-24).
DV_JD = ["uvm","systemverilog","system verilog","verilog","vhdl",
 "formal verification","design verification","specman"]

# Senior markers in the TITLE. Substrings on purpose ('lead' must catch 'Team Leader'/'Leadership';
# Hebrew inflections מנהלת/בכירה). The ambiguous English stems live in SENIOR_TITLE_WORDS and are
# matched WORD-BOUND ('Platform Architecture', 'Expertise', 'Staffing', 'MVP' are not senior).
SENIOR_TITLE = ["senior","sr.","sr ","lead","principal","team lead","teamlead",
 "manager","head of","director","מנהל","בכיר","ראש צוות"]
SENIOR_TITLE_WORDS = ["architect","architects","expert","experts","staff","vp","chief"]

# Student/intern markers - reference list only. Match titles with jobscan.is_student_title()
# (word-bound, TITLE only), never as substrings and never on JD text: 'intern' is inside
# 'internal'/'international', 'מתמחה' in a JD means 'specializing', 'הכשרה' = 'training provided'.
# 'graduate'/'new grad'/'בוגר' are JUNIOR (see JUNIOR_MARK), not student.
STUDENT_MARK = ["student","intern","interns","internship","co-op","trainee","סטודנט","משרת סטודנט"]

# ---- CV variants: Ron's current set (Desktop\Ron - CVs\SUPER_DUPER_FINAL\Ron_Salama_<name>.pdf) ----
# picked by jobscan.pick_cv(): from the TITLE first; JD keyword counts only for generic titles.
CV = {
 "test":"Hardware_Test_Integration",
 "ai":"Software_AI",
 "backend":"Backend_FullStack",
 "clow":"C_Systems",
 "embedded":"Firmware_Embedded",
 "gametech":"GameTech_TechnicalArt",
 "general":"Ron_Salama_CV",
}
