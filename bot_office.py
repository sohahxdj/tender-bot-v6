import os, requests, json, re, hashlib, random, urllib3, html
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = os.getenv("TELEGRAM_TOKEN","").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID","").strip()
SENT_FILE = "sent_office.json"
FACTORIES_FILE = "factories_300.json"
ALGIERS = ZoneInfo("Africa/Algiers")
TODAY = datetime.now(ALGIERS)

print(f"🚀 OFFICE SECTOR BOT - {TODAY.strftime('%d/%m/%Y')}")

# --- نفس القواعد القديمة ---
WILAYAS = ["الجزائر","المرادية","خميستي","جيجل","شرشال","وهران","قسنطينة","بشار","تندوف","ورقلة","بومرداس","تيبازة","البويرة","البليدة","بجاية"]

def load_factories():
    try:
        with open(FACTORIES_FILE,"r",encoding="utf-8") as f:
            return json.load(f)
    except: return []

def load_sent():
    try:
        if os.path.exists(SENT_FILE):
            with open(SENT_FILE,"r",encoding="utf-8") as f:
                data=json.load(f)
                return set(data.get("ids",[])) if isinstance(data, dict) else set(data)
    except: pass
    return set()

def save_sent(s):
    with open(SENT_FILE,"w",encoding="utf-8") as f:
        json.dump({"ids": list(s),"last_update": TODAY.isoformat(),"count": len(s)}, f, ensure_ascii=False, indent=2)

def send(text):
    url=f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data={"chat_id":CHAT_ID,"text":text,"parse_mode":"HTML","disable_web_page_preview":False}
    try:
        r=requests.post(url,data=data,timeout=30)
        return r.status_code==200
    except: return False

def gen_id(t,s):
    clean = re.sub(r'\s+', ' ', t[:200].lower().strip())[:120]
    base = clean + "|" + s
    return hashlib.md5(base.encode()).hexdigest()

def gen_anep(t): return f"26{abs(hash(t))%900000+100000}"

def extract_location(txt):
    m = re.search(r"بولاية\s+([^\s،؛.]+)", txt)
    if m: return m.group(1)
    m = re.search(r"على مستوى\s+([^\s،؛./]+)", txt)
    if m: return m.group(1).split()[0]
    for w in WILAYAS:
        if w in txt: return w
    return "الجزائر"

def choose_nearest(title, factories, n=3):
    if not factories: return []
    loc = extract_location(title).lower()
    scored=[]
    for f in factories:
        f_txt = " ".join([str(f.get(k,"")) for k in ["wilaya","city","address","name"]]).lower()
        score = 0 if loc in f_txt else 1
        scored.append((score,f))
    scored.sort(key=lambda x: x[0])
    nearest=[f for s,f in scored if s==0][:n]
    if len(nearest)<n:
        rest=[f for s,f in scored if s==1]
        random.shuffle(rest)
        nearest+=rest[:n-len(nearest)]
    return nearest[:n]

MONTH_MAP={"جانفي":1,"فيفري":2,"مارس":3,"أفريل":4,"ماي":5,"جوان":6,"جويلية":7,"أوت":8,"اوت":8,"سبتمبر":9,"أكتوبر":10,"نوفمبر":11,"ديسمبر":12}
MONTH_PAT="|".join(sorted([re.escape(k) for k in MONTH_MAP], key=len, reverse=True))

def get_mo(n):
    n=n.lower()
    for k,v in MONTH_MAP.items():
        if k in n: return v
    return None

def extract_dates(txt):
    dates=[]
    for m in re.finditer(rf"(\d{{1,2}})\s+({MONTH_PAT})\s+(20\d{{2}})", txt, flags=re.I):
        mo=get_mo(m.group(2))
        if not mo: continue
        y=int(m.group(3)); d=int(m.group(1))
        if y!=2026 or mo!=8 or d<2: continue
        if d>TODAY.day: continue
        dates.append((y,mo,d, m.group(0)))
    return dates

# --- قطاعك فقط ---
KEYWORDS = ["لوازم مكتب","أدوات مكتب","مستهلكات مكتبية","أوراق","تجهيز مكتب","خزان","خزانات","أواني","أثاث مكتب","قرطاسية","fournitures","bureau","papeterie","vaisselle","réservoir","cuve","armoire","chaise"]

URLS = [
 "https://www.mdn.dz/site_principal/sommaire/appels/appels_ar.php",
 "https://safqatic.dz",
 "https://www.interieur.gov.dz/index.php/ar/اعلانات-طلبات-العروض-والإستشارات"
]

def safe_get(url):
    try:
        headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.mdn.dz/"}
        r=requests.get(url, headers=headers, timeout=30, verify=False)
        if len(r.text)>3000: return r
    except: pass
    return None

def scrape():
    all_tenders=[]
    for url in URLS:
        r=safe_get(url)
        if not r: continue
        print(f"📡 {url} -> {len(r.text)}")
        dates=extract_dates(r.text)
        latest=max(dates, key=lambda x: x[:3]) if dates else (2026,8,TODAY.day,f"{TODAY.day:02d} أوت 2026")
        soup=BeautifulSoup(r.text,"lxml")
        cur=None
        seen=set()
        for el in soup.find_all(['div','p','li','td','tr'], limit=1500):
            txt=el.get_text(" ",strip=True)
            if len(txt)<15: continue
            if len(txt)<120:
                d=extract_dates(txt)
                if d: cur=d[0]; continue
            if len(txt)<30 or len(txt)>4000: continue
            # فلتر القطاع فقط
            if not any(k.lower() in txt.lower() for k in KEYWORDS): continue
            if "طلب العروض" not in txt and "استشارة" not in txt and "consultation" not in txt.lower() and "appel" not in txt.lower():
                continue
            if txt[:100] in seen: continue
            seen.add(txt[:100])
            if not cur: cur=latest
            link=url
            for a in el.find_all('a', href=True):
                if ".pdf" in a['href'].lower() or "download" in a['href'].lower():
                    link=urljoin(url, a['href'])
                    break
            all_tenders.append({"id":gen_id(txt,url),"title":txt,"anep":gen_anep(txt),"link":link,"date":f"{cur[2]:02d}/{cur[1]:02d}/{cur[0]}","source":url})
    print(f"📦 إجمالي قطاع مكاتب/خزانات: {len(all_tenders)}")
    return all_tenders

factories=load_factories()
sent=load_sent()
print(f"🔒 مرسلة سابقا: {len(sent)}")

tenders=scrape()
new=[t for t in tenders if t["id"] not in sent][:10]
print(f"🔍 جديدة: {len(new)}")

if not os.path.exists(SENT_FILE):
    save_sent(sent)

for t in new:
    nearest=choose_nearest(t['title'], factories, 3)
    loc=extract_location(t['title'])
    fac_txt=""
    for i,f in enumerate(nearest,1):
        name=html.escape(f.get('name','')[:45])
        phone_raw=str(f.get('phone','')).strip()
        phone=f"\u200E{phone_raw}\u200E"
        murl=f.get('map') or f.get('maps') or f"https://www.google.com/maps/search/{name}+{loc}"
        fac_txt+=f"{i}. 🏭 <b>{name}</b> ({loc}) 📞 <code>{phone}</code> | <a href='{murl}'>🗺️ خريطة</a>\n"
    msg=f"""🔔 <b>[{t['date']}] {loc} - قطاع مكاتب/خزانات</b>\n\nANEP: {t['anep']}\n📋 {html.escape(t['title'][:700])}\n\n📄 <a href="{t['link']}">📎 الإعلان الأصلي + PDF</a>\n🔗 المصدر: {t['source']}\n\n🏭 <b>أقرب 3 موردين:</b>\n{fac_txt}"""
    if send(msg):
        sent.add(t["id"])

save_sent(sent)
print(f"🏁 محفوظ {len(sent)}")
