#!/usr/bin/env python3
"""Low-volume ICN international passenger-flight monitor using IIAC official open API."""
from __future__ import annotations
import json, os, re, sys, time, urllib.parse, urllib.request, urllib.error, pathlib, statistics
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
BASE = "https://apis.data.go.kr/B551177/statusOfAllFltDeOdp"
OPS = {"departure": "getFltDeparturesDeOdp", "arrival": "getFltArrivalsDeOdp"}
DOMESTIC = {"GMP","CJU","PUS","TAE","CJJ","KWJ","RSU","USN","YNY","WJU","KPO","HIN","MWX","KUV","MPK","JDG","JIN","OSN","SSN","CHF"}
DONE = {"departure":{"출발","출발완료","departed","airborne"}, "arrival":{"도착","도착완료","arrived","landed"}}
CANCEL = {"결항","취소","cancelled","canceled"}

class DataError(RuntimeError): pass

def norm(s): return re.sub(r"[^a-z0-9가-힣]", "", str(s or "").lower())
def pick(d, *names):
    d = {norm(k):v for k,v in d.items()}
    for n in names:
        v=d.get(norm(n))
        if v is not None and str(v).strip(): return v
    return None

def parse_dt(v):
    if not v: return None
    s=str(v).strip()
    try:
        if s.isdigit() and len(s)==14:
            return datetime.strptime(s,"%Y%m%d%H%M%S").replace(tzinfo=KST)
        if s.isdigit() and len(s)==12:
            return datetime.strptime(s,"%Y%m%d%H%M").replace(tzinfo=KST)
        for fmt in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%Y/%m/%d %H:%M"):
            try: return datetime.strptime(s,fmt).replace(tzinfo=KST)
            except ValueError: pass
        d=datetime.fromisoformat(s.replace("Z","+00:00"))
        return d.replace(tzinfo=KST) if d.tzinfo is None else d.astimezone(KST)
    except ValueError: return None

def status_of(raw, direction):
    s=norm(raw)
    if not s: return "unknown"
    if s in {norm(x) for x in CANCEL} or "결항" in s or "cancel" in s: return "cancelled"
    if s in {norm(x) for x in DONE[direction]}: return "completed"
    if "지연" in s or "delay" in s: return "delayed"
    if s in {"정상","예정","운항예정","탑승중","수속중","scheduled","boarding","ontime","ontime"}: return "pending"
    return "unknown"

def get_page(url, params):
    req=urllib.request.Request(url+"?"+urllib.parse.urlencode(params),headers={"User-Agent":"ICN-Flight-Monitor/2.0","Accept":"application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=25) as r: raw=r.read(8_000_000)
            try: obj=json.loads(raw)
            except Exception as e: raise DataError("API 응답이 JSON이 아닙니다") from e
            resp=obj.get("response",obj); header=resp.get("header",{})
            code=str(pick(header,"resultCode","code") or "00")
            if code not in {"00","0","NORMAL_SERVICE","SUCCESS"}:
                raise DataError("공식 API 오류: "+str(pick(header,"resultMsg","message") or code))
            body=resp.get("body",{})
            total=pick(body,"totalCount","total")
            if total is None: raise DataError("API totalCount 누락")
            items=body.get("items",{})
            if isinstance(items,dict): items=items.get("item",[])
            if items is None: items=[]
            if isinstance(items,dict): items=[items]
            if not isinstance(items,list): raise DataError("항공편 목록 구조 오류")
            return items,int(total)
        except urllib.error.HTTPError as e:
            detail=e.read(2000).decode("utf-8","replace").strip()
            raise DataError(f"공식 API HTTP {e.code}: {detail or e.reason}") from e
        except (urllib.error.URLError,TimeoutError) as e:
            if attempt==2: raise DataError("API 통신 실패: "+str(e)) from e
            time.sleep(2**attempt)
    raise DataError("API 요청 실패")

def fetch(key,direction,start,end):
    day=start.strftime("%Y%m%d")
    url=BASE+"/"+OPS[direction]
    all_rows=[]; expected=None
    for page in range(1,21):
        params={"serviceKey":key,"pageNo":page,"numOfRows":1000,"searchdtCode":"S",
                "searchDate":day,"searchFrom":start.strftime("%H%M"),
                "searchTo":(end-timedelta(minutes=1)).strftime("%H%M"),
                "passengerOrCargo":"P","type":"json"}
        rows,total=get_page(url,params)
        if expected is None: expected=total
        elif expected!=total: raise DataError("페이지 조회 중 totalCount 변경")
        all_rows.extend(rows)
        if len(all_rows)>=expected: return all_rows
        if not rows: break
    raise DataError(f"페이지 누락: {len(all_rows)}/{expected}")

def normalize(rows,direction,start,end):
    flights={}
    for r in rows:
        rawdt=pick(r,"scheduleDateTime","scheduledDateTime","scheduleDatetime","scheduledDatetime","scheduleDt","scheduleTime")
        dt=parse_dt(rawdt)
        if dt is None: raise DataError("예정 일시 필드 확인 실패")
        if not start<=dt<end: raise DataError("조회 시간대 밖의 항공편 반환")
        flight=str(pick(r,"flightId","flightNumber","flightNo") or "").upper().strip()
        master=str(pick(r,"masterFlightId","masterFlight","masterFlightNumber","masterFlightNo") or "").upper().strip()
        fid=str(pick(r,"fid","flightUniqCode") or "").strip()
        if not (flight or master or fid): raise DataError("편명 식별자 누락")
        airport=str(pick(r,"airportCode","counterpartAirportCode","originAirportCode","destinationAirportCode") or "").upper().strip()
        if not re.fullmatch(r"[A-Z]{3}",airport): raise DataError("상대 공항코드 누락: 국제선 필터 검증 불가")
        codeshare=norm(pick(r,"codeShare","codeShareYn","codeshareFlag"))
        if codeshare in {"y","yes","true","1"} and not master: raise DataError("코드셰어 마스터편명 누락")
        if airport in DOMESTIC: continue
        identity=master or flight or fid
        k=dt.strftime("%Y%m%d%H%M")+"|"+identity
        rawstatus=str(pick(r,"flightStatus","flightStatusName","status","statusName","operateStatus","operationStatus","flightState","remark") or "")
        item={"scheduled":dt.isoformat(),"flight":flight,"master":master,"airline":str(pick(r,"airline","airlineName","airlineCode") or ""),
              "airport":airport,"status_raw":rawstatus,"status":status_of(rawstatus,direction)}
        old=flights.get(k)
        priority={"unknown":0,"pending":1,"delayed":2,"completed":3,"cancelled":4}
        if old is None or priority[item["status"]]>priority[old["status"]]: flights[k]=item
    return list(flights.values())

def stats(rows, asof):
    n=len(rows); done=sum(x["status"]=="completed" for x in rows); cancel=sum(x["status"]=="cancelled" for x in rows)
    pending=sum(x["status"]=="pending" for x in rows); delayed=sum(x["status"]=="delayed" for x in rows); unknown=sum(x["status"]=="unknown" for x in rows)
    return {"planned":n,"completed_confirmed":done,"cancelled_confirmed":cancel,"delayed_unconfirmed":delayed,
            "pending":pending,"unknown_status":unknown,"unresolved":pending+delayed+unknown,
            "cancel_rate_pct":round(cancel*100/n,2) if n else None,"observed_at":asof.isoformat()}

def atomic(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); tmp.replace(path)

def run(asof,key):
    end=asof.replace(hour=(asof.hour//4)*4,minute=0,second=0,microsecond=0)
    start=end-timedelta(hours=4)
    results={}
    for direction in OPS:
        rows=normalize(fetch(key,direction,start,end),direction,start,end)
        results[direction]=stats(rows,asof)
    DATA.mkdir(parents=True,exist_ok=True)
    hist_path=DATA/"history.json"
    history=json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}
    for direction,s in results.items():
        history[start.isoformat()+"|"+direction]={"window_end":end.isoformat(),**s}
        prior=[]
        for day in range(1,8):
            k=(start-timedelta(days=day)).isoformat()+"|"+direction
            x=history.get(k)
            if x and x.get("unresolved")==0: prior.append(x["completed_confirmed"])
        if len(prior)==7 and s["unresolved"]==0:
            avg=statistics.mean(prior); s["reference_7d_avg"]=round(avg,1)
            s["delta_7d_pct"]=round((s["completed_confirmed"]-avg)*100/avg,1) if avg else None
        else:
            s["reference_7d_avg"]=None; s["delta_7d_pct"]=None; s["baseline_days"]=len(prior)
    cutoff=(asof-timedelta(days=30)).isoformat()
    history={k:v for k,v in history.items() if k.split("|")[0]>=cutoff}
    latest={"airport":"ICN","scope":"international_passenger","source":"IIAC official statusOfAllFltDeOdp API; scheduled-time query",
            "as_of":asof.isoformat(),"window_start":start.isoformat(),"window_end":end.isoformat(),
            "quality":"PARTIAL" if any(v["unresolved"] for v in results.values()) else "STATUS_CLASSIFIED",
            "directions":results,
            "limitations":["완료편은 공식 API의 명시적 출발/도착 상태 기준이며 레이더·관제 실측이 아님",
                           "국내선 제외는 상대 공항 IATA 코드 목록 기준이며 코드셰어 중복 제거는 마스터편명 기준",
                           "7일 기준선은 동일 4시간대의 완전한 7일 자료가 축적된 후 제공"]}
    atomic(hist_path,history); atomic(DATA/"latest.json",latest)
    md=["# 인천공항 국제선 여객기 운항 모니터",f"- 수집시각: {asof.isoformat()} KST",f"- 대상시간: {start.isoformat()} ~ {end.isoformat()}",f"- 데이터 품질: {latest['quality']}","",
        "| 방향 | 계획편 | 출도착 확인편 | 결항 | 결항률 | 미확정 | 최근 7일 대비 |","|---|---:|---:|---:|---:|---:|---:|"]
    for d,label in (("departure","출발"),("arrival","도착")):
        s=results[d]; delta=f"{s['delta_7d_pct']}%" if s["delta_7d_pct"] is not None else "기준선 미확보"
        md.append(f"| {label} | {s['planned']} | {s['completed_confirmed']} | {s['cancelled_confirmed']} | {s['cancel_rate_pct']}% | {s['unresolved']} | {delta} |")
    md+=["","완료편은 해당 시간대에 예정된 편 중 API 상태가 출발/도착으로 명시된 편수입니다. 실제 활주로 이착륙 계측과 동일하지 않습니다.","API 실패 또는 필드 불일치 시 보고서를 갱신하지 않고 Actions 실행을 실패 처리합니다."]
    (DATA/"latest.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print(json.dumps(latest,ensure_ascii=False))
    return latest

if __name__=="__main__":
    key=os.getenv("DATA_GO_KR_SERVICE_KEY","").strip()
    if not key:
        print("DATA_COLLECTION_FAILED: DATA_GO_KR_SERVICE_KEY secret missing",file=sys.stderr); sys.exit(2)
    try: run(datetime.now(KST),key)
    except Exception as e:
        print("DATA_COLLECTION_FAILED: "+str(e),file=sys.stderr); sys.exit(1)
