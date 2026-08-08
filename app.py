
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import swisseph as swe
import math

BASE = Path(__file__).resolve().parent
app = FastAPI(title="AstroMatch V7")

SIGNS = ["Ariete","Toro","Gemelli","Cancro","Leone","Vergine","Bilancia","Scorpione","Sagittario","Capricorno","Acquario","Pesci"]
ELEMENT = {"Ariete":"Fuoco","Leone":"Fuoco","Sagittario":"Fuoco","Toro":"Terra","Vergine":"Terra","Capricorno":"Terra",
            "Gemelli":"Aria","Bilancia":"Aria","Acquario":"Aria","Cancro":"Acqua","Scorpione":"Acqua","Pesci":"Acqua"}
PLANETS = {
    "Sole":swe.SUN,"Luna":swe.MOON,"Mercurio":swe.MERCURY,"Venere":swe.VENUS,"Marte":swe.MARS,
    "Giove":swe.JUPITER,"Saturno":swe.SATURN,"Urano":swe.URANUS,"Nettuno":swe.NEPTUNE,"Plutone":swe.PLUTO,
}
PWEIGHT={"Sole":4,"Luna":4,"Mercurio":3,"Venere":4,"Marte":4,"Giove":2,"Saturno":3,"Urano":1,"Nettuno":1,"Plutone":2}
ASPECTS={"Congiunzione":(0,7),"Sestile":(60,4.5),"Quadratura":(90,6),"Trigono":(120,6),"Opposizione":(180,6)}
RULERS={"Ariete":"Marte","Toro":"Venere","Gemelli":"Mercurio","Cancro":"Luna","Leone":"Sole","Vergine":"Mercurio",
        "Bilancia":"Venere","Scorpione":"Plutone","Sagittario":"Giove","Capricorno":"Saturno","Acquario":"Urano","Pesci":"Nettuno"}

class Person(BaseModel):
    name:str="Persona"
    date:str
    time:str
    timezone:str="Europe/Rome"
    latitude:float
    longitude:float
    domicile_city:str=""
    work:str=""
    house_system:str="P"

class MatchRequest(BaseModel):
    person_a:Person
    candidates:list[Person]=Field(default_factory=list)
    preferred_work:str=""
    preferred_city:str=""

def norm(x): return x%360
def sign_at(lon):
    i=int(norm(lon)//30); deg=norm(lon)-i*30
    return {"name":SIGNS[i],"degree":round(deg,2),"element":ELEMENT[SIGNS[i]]}

def jd_for(p):
    tz_name=(p.timezone or "Europe/Rome").strip()
    aliases={
        "Europe/Rome":"Europe/Rome",
        "Europe\\Rome":"Europe/Rome",
        "Italia":"Europe/Rome",
        "Italy":"Europe/Rome",
        "UTC+1":"Etc/GMT-1",
        "UTC+2":"Etc/GMT-2",
    }
    tz_name=aliases.get(tz_name,tz_name)
    try:
        tz=ZoneInfo(tz_name)
    except Exception as exc:
        raise ValueError(
            f"Fuso orario non disponibile: {tz_name}. "
            "Il pacchetto AstroMatch include tzdata; riavvia il launcher "
            "per completare l'installazione."
        ) from exc
    local=datetime.fromisoformat(p.date+"T"+p.time).replace(tzinfo=tz)
    utc=local.astimezone(ZoneInfo("UTC"))
    return swe.julday(utc.year,utc.month,utc.day,utc.hour+utc.minute/60+utc.second/3600)

def house_number(lon,cusps):
    lon=norm(lon)
    for i in range(12):
        a=norm(cusps[i]); b=norm(cusps[(i+1)%12])
        if i==11:
            if lon>=a or lon<b: return 12
        elif a<=lon<b: return i+1
    return 1

def chart(p):
    jd=jd_for(p)
    house_result=swe.houses_ex(jd,p.latitude,p.longitude,p.house_system.encode()[:1])
    if not isinstance(house_result,(tuple,list)) or len(house_result)<2:
        raise RuntimeError(f"Formato houses_ex inatteso: {house_result!r}")
    cusps, ascmc=house_result[0], house_result[1]
    if len(house_result)>2 and house_result[2]:
        raise RuntimeError(str(house_result[2]))
    # pysweph >=2.10.3.4 returns house cusps with an empty item at index 0.
    raw_cusps=list(cusps)
    if len(raw_cusps)>=13 and abs(float(raw_cusps[0])) < 1e-12:
        raw_cusps=raw_cusps[1:]
    cusps=[norm(x) for x in raw_cusps[:12]]
    if len(cusps)!=12:
        raise RuntimeError(f"Formato cuspidi inatteso: {len(cusps)} valori")
    angles={"Ascendente":norm(ascmc[0]),"Medio Cielo":norm(ascmc[1]),
            "Vertex":norm(ascmc[3]) if len(ascmc)>3 else None}
    angles["Discendente"]=norm(angles["Ascendente"]+180)
    angles["Imum Coeli"]=norm(angles["Medio Cielo"]+180)
    positions={}
    for name,body in PLANETS.items():
        calc_result=swe.calc_ut(jd,body,swe.FLG_MOSEPH|swe.FLG_SPEED)
        if not isinstance(calc_result,(tuple,list)) or len(calc_result)<2:
            raise RuntimeError(f"Formato calc_ut inatteso per {name}: {calc_result!r}")
        xx,ret=calc_result[0],calc_result[1]
        if len(calc_result)>2 and calc_result[2]:
            raise RuntimeError(str(calc_result[2]))
        lon=norm(xx[0]); positions[name]={
            "longitude":round(lon,5),"sign":sign_at(lon),
            "retrograde":xx[3]<0,"speed":round(xx[3],5),
            "house":house_number(lon,cusps)
        }
    angle_out={k:({"longitude":round(v,5),"sign":sign_at(v)} if v is not None else None) for k,v in angles.items()}
    return {"input":p.model_dump(),"positions":positions,
            "angles":angle_out,
            "houses":[{"house":i+1,"cusp":round(cusps[i],5),"sign":sign_at(cusps[i])} for i in range(12)]}

def angle_diff(a,b):
    d=abs(norm(a)-norm(b)); return min(d,360-d)

def aspects(a,b):
    out=[]
    for pa,va in a["positions"].items():
        for pb,vb in b["positions"].items():
            d=angle_diff(va["longitude"],vb["longitude"])
            for name,(target,orb) in ASPECTS.items():
                if abs(d-target)<=orb:
                    strength=(PWEIGHT[pa]+PWEIGHT[pb])/2 * max(.1,1-abs(d-target)/orb)
                    if name in ("Trigono","Sestile"): sign=1
                    elif name=="Congiunzione": sign=.45
                    else: sign=-.45
                    out.append({"a":pa,"b":pb,"aspect":name,"orb":round(abs(d-target),2),
                                "score":round(strength,3),"signed":round(strength*sign,3)})
                    break
    return sorted(out,key=lambda x:x["score"],reverse=True)

def overlays(base,cand):
    res={"5":[],"7":[],"8":[],"4":[]}
    cusps=[x["cusp"] for x in base["houses"]]
    for p,v in cand["positions"].items():
        h=house_number(v["longitude"],cusps)
        if str(h) in res: res[str(h)].append(p)
    return res

def synastry_score(a,b):
    asp=aspects(a,b)
    cats={"emotional":0,"attraction":0,"partnership":0,"communication":0,"stability":0,"intimacy":0}
    for x in asp:
        pair={x["a"],x["b"]}; s=x["signed"]
        if pair & {"Sole","Luna"}: cats["emotional"]+=s*2
        if pair & {"Venere","Marte"}: cats["attraction"]+=s*2.2
        if pair & {"Mercurio"}: cats["communication"]+=s*1.4
        if pair & {"Saturno"}: cats["stability"]+=s*1.7
        if pair & {"Plutone","Marte","Venere"}: cats["intimacy"]+=s*1.25
        if pair & {"Sole","Luna","Venere","Marte","Saturno"}: cats["partnership"]+=s*.8
    ov=overlays(a,b)
    for p in ov["5"]: cats["attraction"]+=PWEIGHT[p]*1.8
    for p in ov["7"]: cats["partnership"]+=PWEIGHT[p]*2.2; cats["stability"]+=PWEIGHT[p]*.4
    for p in ov["8"]: cats["intimacy"]+=PWEIGHT[p]*1.8
    for p in ov["4"]: cats["emotional"]+=PWEIGHT[p]*.8
    vals={k:round(max(0,min(100,50+v*2.2)),1) for k,v in cats.items()}
    return vals,asp,ov

def ideal_score(base,cand):
    dsc=base["angles"]["Discendente"]["sign"]["name"]
    sun=cand["positions"]["Sole"]["sign"]["name"]
    moon=cand["positions"]["Luna"]["sign"]["name"]
    ven=cand["positions"]["Venere"]["sign"]["name"]
    mar=cand["positions"]["Marte"]["sign"]["name"]
    def elem(s): return ELEMENT[s]
    score=50
    if sun==dsc: score+=18
    if elem(sun)==elem(dsc): score+=8
    if elem(moon)==elem(base["positions"]["Luna"]["sign"]["name"]): score+=8
    if elem(ven)==elem(base["positions"]["Venere"]["sign"]["name"]): score+=6
    if elem(mar)==elem(base["positions"]["Marte"]["sign"]["name"]): score+=6
    ov=overlays(base,cand)
    score+=min(12,len(ov["7"])*4)
    score+=min(8,len(ov["5"])*2)
    return round(max(0,min(100,score)),1)

def final_match(base,cand,prefs):
    cats,asp,ov=synastry_score(base,cand)
    ideal=ideal_score(base,cand)
    chemistry=cats["attraction"]*.55+cats["intimacy"]*.25+cats["emotional"]*.20
    longterm=cats["partnership"]*.30+cats["stability"]*.25+cats["emotional"]*.25+cats["communication"]*.20
    practical=50
    pw=(prefs.get("preferred_work") or "").lower().strip()
    pc=(prefs.get("preferred_city") or "").lower().strip()
    hits=0; total=0
    if pw: total+=1; hits += pw in (cand["input"].get("work") or "").lower()
    if pc: total+=1; hits += pc in (cand["input"].get("domicile_city") or "").lower()
    if total: practical=50+50*hits/total
    final=.42*chemistry+.43*longterm+.10*ideal+.05*practical
    if final>=90: band="Eccezionale"
    elif final>=82: band="Molto alta"
    elif final>=74: band="Alta"
    elif final>=65: band="Buona"
    elif final>=55: band="Media"
    else: band="Bassa"
    return {"score":round(final,1),"band":band,"categories":cats,
            "chemistry":round(chemistry,1),"long_term":round(longterm,1),
            "ideal":ideal,"practical":round(practical,1),"aspects":asp,"overlays":ov}


def ideal_partner_profile(base):
    """
    Costruisce un profilo astrologico ideale come configurazione interpretativa,
    senza fingere che esista una persona reale con quei dati.
    Ottimizza una griglia di possibili segni per Sole/Luna/Venere/Marte/Ascendente
    usando le stesse regole di compatibilità del motore.
    """
    base_signs = {
        "sun": base["positions"]["Sole"]["sign"]["name"],
        "moon": base["positions"]["Luna"]["sign"]["name"],
        "venus": base["positions"]["Venere"]["sign"]["name"],
        "mars": base["positions"]["Marte"]["sign"]["name"],
        "asc": base["angles"]["Ascendente"]["sign"]["name"],
        "desc": base["angles"]["Discendente"]["sign"]["name"],
    }

    # Compatibility heuristics used consistently with the rest of the engine.
    compatible_elements = {
        "Fuoco": {"Fuoco": 1.0, "Aria": .85, "Acqua": .45, "Terra": .55},
        "Terra": {"Terra": 1.0, "Acqua": .85, "Fuoco": .55, "Aria": .60},
        "Aria": {"Aria": 1.0, "Fuoco": .85, "Terra": .60, "Acqua": .55},
        "Acqua": {"Acqua": 1.0, "Terra": .85, "Aria": .55, "Fuoco": .45},
    }
    sign_index = {s:i for i,s in enumerate(SIGNS)}

    def sign_relation(a,b):
        ia, ib = sign_index[a], sign_index[b]
        d=min((ia-ib)%12,(ib-ia)%12)
        # same sign / sextile / trine / opposition / square / quincunx-ish
        return {0:1.00,1:.62,2:.88,3:.96,4:.52,5:.82,6:.48}.get(d,.62)

    def element_relation(a,b):
        return compatible_elements[ELEMENT[a]][ELEMENT[b]]

    def score_combo(sun, moon, venus, mars, asc):
        # Weight the relationship factors; Descendant is opposite Ascendant.
        desc = SIGNS[(sign_index[asc]+6)%12]
        score = 0.0
        score += 24 * sign_relation(desc, sun)
        score += 18 * element_relation(base_signs["moon"], moon)
        score += 15 * sign_relation(base_signs["venus"], venus)
        score += 15 * sign_relation(base_signs["mars"], mars)
        score += 10 * element_relation(base_signs["sun"], sun)
        score += 8 * sign_relation(base_signs["asc"], asc)
        # Reward complementary relationship axes.
        score += 10 * sign_relation(base_signs["desc"], asc)
        return score

    # Search the strongest configuration over the 12^5 discrete sign grid.
    # This is small enough to be deterministic and local.
    best = None
    for sun in SIGNS:
        for moon in SIGNS:
            for venus in SIGNS:
                for mars in SIGNS:
                    for asc in SIGNS:
                        s = score_combo(sun, moon, venus, mars, asc)
                        candidate = (s, sun, moon, venus, mars, asc)
                        if best is None or candidate > best:
                            best = candidate

    raw, sun, moon, venus, mars, asc = best
    desc = SIGNS[(sign_index[asc]+6)%12]

    # Produce a coherent house emphasis from the ideal Ascendant.
    ideal_houses = {
        "Casa 1": asc,
        "Casa 5": SIGNS[(sign_index[asc]+4)%12],
        "Casa 7": desc,
        "Casa 8": SIGNS[(sign_index[asc]+7)%12],
        "Casa 10": SIGNS[(sign_index[asc]+9)%12],
    }

    # The exact outer-planet signs are not optimized here because their
    # generational nature makes them poor individual selectors.
    outer = {
        "Giove": base["positions"]["Giove"]["sign"]["name"],
        "Saturno": base["positions"]["Saturno"]["sign"]["name"],
        "Urano": base["positions"]["Urano"]["sign"]["name"],
        "Nettuno": base["positions"]["Nettuno"]["sign"]["name"],
        "Plutone": base["positions"]["Plutone"]["sign"]["name"],
    }

    # Convert the raw heuristic score to a user-facing percentage.
    # Keep it explicitly as a model score, not a scientific probability.
    ideal_score = round(max(0, min(100, 65 + (raw/100)*35)), 1)

    return {
        "model_score": ideal_score,
        "profile": {
            "Sole": sun, "Luna": moon, "Ascendente": asc,
            "Mercurio": "da verificare sul tema reale",
            "Venere": venus, "Marte": mars, **outer
        },
        "relationship_axis": {"Ascendente ideale": asc, "Discendente ideale": desc},
        "ideal_houses": ideal_houses,
        "why": [
            f"Il Sole ideale in {sun} massimizza l'asse di partnership rispetto al Discendente di {base_signs['desc']}.",
            f"La Luna in {moon} è scelta per la migliore sintonia elementale con la Luna in {base_signs['moon']}.",
            f"Venere in {venus} e Marte in {mars} privilegiano attrazione e stile affettivo coerenti con il tema.",
            f"L'Ascendente in {asc} crea l'asse relazionale con il Discendente in {desc}."
        ],
        "search_targets": {
            "priorita_alta": ["Sole", "Luna", "Ascendente", "Venere", "Marte"],
            "da_confrontare": ["Mercurio", "Giove", "Saturno", "Casa 5", "Casa 7", "Casa 8"],
            "nota": "Il profilo è un target astrologico interpretativo: per valutare una persona reale servono i suoi dati completi."
        }
    }



@app.get("/api/geocode")
def geocode_city(q: str):
    q=(q or "").strip()
    if len(q)<2:
        return {"results":[]}
    import urllib.parse, urllib.request, json as _json
    params=urllib.parse.urlencode({
        "q": q,
        "format": "jsonv2",
        "limit": 6,
        "addressdetails": 1,
        "accept-language": "it"
    })
    url="https://nominatim.openstreetmap.org/search?"+params
    req=urllib.request.Request(url, headers={
        "User-Agent":"AstroMatch/11.0 (local astrology application)"
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data=_json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(502, f"Geocodifica non disponibile: {exc}")
    results=[]
    for item in data:
        address=item.get("address",{})
        city=(address.get("city") or address.get("town") or
              address.get("village") or address.get("municipality") or "")
        country=address.get("country","")
        label=item.get("display_name","")
        results.append({
            "label":label,
            "city":city,
            "country":country,
            "latitude":float(item["lat"]),
            "longitude":float(item["lon"])
        })
    return {"results":results}


@app.get("/api/health")
def health():
    return {
        "status":"ok",
        "engine":"Swiss Ephemeris / Moshier",
        "external_ephemeris_files":False,
        "city_search":"OpenStreetMap Nominatim (worldwide)"
    }

@app.get("/")
def home():
    index=BASE/"static"/"index.html"
    if not index.exists():
        raise HTTPException(500, "Interfaccia AstroMatch mancante: static/index.html")
    return FileResponse(index)

@app.post("/api/chart")
def api_chart(p:Person):
    try: return chart(p)
    except Exception as e: raise HTTPException(400,str(e))


@app.post("/api/ideal")
def api_ideal(p:Person):
    try:
        base = chart(p)
        return {"person_a": base, "ideal": ideal_partner_profile(base)}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/match")
def api_match(req:MatchRequest):
    if not req.candidates: raise HTTPException(400,"Aggiungi almeno un candidato.")
    try:
        base=chart(req.person_a); prefs={"preferred_work":req.preferred_work,"preferred_city":req.preferred_city}
        rows=[]
        for c in req.candidates:
            cc=chart(c); m=final_match(base,cc,prefs)
            rows.append({"candidate":c.model_dump(),"match":m})
        rows.sort(key=lambda x:x["match"]["score"],reverse=True)
        if rows:
            for i,r in enumerate(rows):
                r["rank"]=i+1
                r["why"]=sorted(r["match"]["categories"].items(),key=lambda x:x[1],reverse=True)[:3]
            if len(rows)>1:
                rows[0]["why_winner"]=f"Supera il #2 ({rows[1]['candidate']['name']}) di {round(rows[0]['match']['score']-rows[1]['match']['score'],1)} punti."
        return {"person_a":base,"ranking":rows}
    except Exception as e: raise HTTPException(400,str(e))

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.environ.get("PORT","10000")))
