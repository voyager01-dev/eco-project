# main.py
import json
import re
from typing import List

import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------------------------
# 기본 설정
# ---------------------------
st.set_page_config(page_title="탄소발자국 대시보드", layout="wide")
TZ_NAME = st.secrets.get("TIMEZONE", "Asia/Seoul")
SHEET_ID = st.secrets["SHEET_ID"]
SHEET_NAME = st.secrets.get("SHEET_NAME", "Form Responses 1")

# ---------------------------
# Google Sheets 연결
# ---------------------------
@st.cache_resource
def gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds_json = st.secrets["GSHEETS_CREDENTIALS"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds_json), scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_sheet(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    ws = gsheet_client().open_by_key(sheet_id).worksheet(sheet_name)
    rows = ws.get_all_records()  # 1행을 헤더로 사용
    df = pd.DataFrame(rows)
    return df

# ---------------------------
# 유틸
# ---------------------------
def to_num(s: pd.Series):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def guess(cols: List[str], keywords: List[str]):
    """컬럼명에서 한국어/영문 키워드로 가장 잘 매칭되는 후보를 찾아 반환"""
    pat = re.compile("|".join([re.escape(k) for k in keywords]), re.IGNORECASE)
    for c in cols:
        if pat.search(str(c)):  # 키워드가 컬럼명에 포함되면
            return c
    return None

# ---------------------------
# 데이터 로드
# ---------------------------
st.title("우리 반 디지털 탄소발자국 대시보드")

df_raw = load_sheet(SHEET_ID, SHEET_NAME)
if df_raw.empty:
    st.warning("시트가 비어 있습니다. 설문 응답이 들어오면 자동으로 갱신돼요.")
    st.stop()

cands = list(df_raw.columns)

# ---------------------------
# 컬럼 자동 추정(설문 질문 이름과 느슨 매칭)
# Forms 타임스탬프는 보통 "Timestamp" 또는 "응답 시간"
# ---------------------------
auto_date   = guess(cands, ["Timestamp","응답","제출","날짜","date"])
auto_grade  = guess(cands, ["학년","grade"])
auto_class  = guess(cands, ["반","class"])
auto_team   = guess(cands, ["팀","모둠","조","team"])
auto_id     = guess(cands, ["익명","별명","ID","아이디","학번","anon"])

auto_youtube   = guess(cands, ["유튜브","youtube"])
auto_streaming = guess(cands, ["스트리밍","넷플릭스","웨이브","watch","video(기타)"])
auto_sns       = guess(cands, ["인스타","틱톡","SNS"])
auto_msg       = guess(cands, ["카카오톡","카톡","메신저","kakao","messenger"])
auto_meeting   = guess(cands, ["화상","회의","미트","줌","zoom","meet"])

auto_mobile_mb = guess(cands, ["데이터","MB","GB","와이파이 사용량"])

auto_commute_mode = guess(cands, ["교통수단","통학 수단","등하교 수단","이동 수단","교통"])
auto_commute_km   = guess(cands, ["거리","km","킬로"])

auto_lunch_type = guess(cands, ["점심","메뉴","식단","채식","육식","혼합"])
auto_delivery   = guess(cands, ["배달","포장"])
auto_pet        = guess(cands, ["페트","생수","병"])
auto_cup        = guess(cands, ["일회용","컵"])
auto_recycle    = guess(cands, ["재활용","분리배출"])
auto_cleanup    = guess(cands, ["정리","이메일","파일","디지털","청소","cleanup","delete"])

# ---------------------------
# 사이드바: 컬럼 매핑
# ---------------------------
st.sidebar.header("컬럼 매핑 (설문 질문 연결)")
def pick(label, default=None):
    options = ["(없음)"] + cands
    idx = options.index(default) if default in options else 0
    return st.sidebar.selectbox(label, options, index=idx)

col_date   = pick("날짜/타임스탬프", auto_date or "Timestamp")
col_grade  = pick("학년",  auto_grade)
col_class  = pick("반",    auto_class)
col_team   = pick("팀/모둠/조", auto_team)
col_id     = pick("익명 ID/학번 일부/별명", auto_id)

# 사용시간(분)
col_youtube   = pick("유튜브 사용시간(분)", auto_youtube)
col_streaming = pick("기타 스트리밍(분)", auto_streaming)
col_sns       = pick("SNS(인스타/틱톡, 분)", auto_sns)
col_msg       = pick("메신저(카톡, 분)", auto_msg)
col_meeting   = pick("화상수업/회의(분)", auto_meeting)
# 데이터 사용량
col_mobile_mb = pick("모바일 데이터 사용량(MB)", auto_mobile_mb)

# 이동/식생활/소비
col_commute_mode = pick("등하교 교통수단", auto_commute_mode)
col_commute_km   = pick("등하교 거리(km)", auto_commute_km)
col_lunch_type   = pick("점심 유형(육/혼합/채식)", auto_lunch_type)
col_delivery     = pick("배달 이용(yes/no)", auto_delivery)
col_pet          = pick("페트병 개수", auto_pet)
col_cup          = pick("일회용 컵 개수", auto_cup)
col_recycle      = pick("재활용/분리배출(횟수/봉투수)", auto_recycle)
col_cleanup      = pick("디지털 정리(분)", auto_cleanup)

# ---------------------------
# 표준 스키마로 변환
# ---------------------------
df = pd.DataFrame()

# 날짜
if col_date != "(없음)" and col_date in df_raw.columns:
    # 폼 타임스탬프가 문자열/현지시간일 수 있으므로 일단 파싱만
    df["date"] = pd.to_datetime(df_raw[col_date], errors="coerce").dt.date
else:
    df["date"] = pd.NaT

# 식별/분류
def col_to_str(cname):
    return df_raw[cname].astype(str) if (cname!="(없음)" and cname in df_raw.columns) else ""

df["grade"]   = col_to_str(col_grade)
df["class"]   = col_to_str(col_class)
df["team"]    = col_to_str(col_team)
df["anon_id"] = col_to_str(col_id)

# 시간/숫자
def col_to_num(cname):
    return to_num(df_raw[cname]) if (cname!="(없음)" and cname in df_raw.columns) else 0

df["youtube_min"]       = col_to_num(col_youtube)
df["streaming_min"]     = col_to_num(col_streaming)
df["sns_min"]           = col_to_num(col_sns)
df["messenger_min"]     = col_to_num(col_msg)
df["video_meeting_min"] = col_to_num(col_meeting)
df["mobile_data_mb"]    = col_to_num(col_mobile_mb)

df["commute_mode"] = col_to_str(col_commute_mode).str.lower()
df["commute_km"]   = col_to_num(col_commute_km)

df["lunch_type"]   = col_to_str(col_lunch_type).str.lower()
df["delivery_used"] = col_to_str(col_delivery).str.lower()
df["pet_bottles"]  = col_to_num(col_pet)
df["disposable_cups"] = col_to_num(col_cup)
df["recycle_bags"] = col_to_num(col_recycle)
df["digital_cleanup_min"] = col_to_num(col_cleanup)

# ---------------------------
# 교육용 간이 배출계수 & 계산
# ---------------------------
K_STREAMING_PER_HR = 0.08   # kg CO2e
K_SNS_PER_HR       = 0.04
K_MSG_PER_HR       = 0.02
K_MEET_PER_HR      = 0.15
K_MOBILE_PER_GB    = 0.05

VEH_COEF = {"subway":0.04, "bus":0.08, "car":0.18, "carpool":0.09, "walk":0.0, "bike":0.0}
K_PET = 0.08
K_CUP = 0.03
K_DELIVERY = 0.5
LUNCH_COEF = {"veg":0.5, "mixed":1.2, "meat":2.0}

# 분→시간
df["youtube_hr"]        = df["youtube_min"] / 60
df["streaming_hr"]      = df["streaming_min"] / 60
df["sns_hr"]            = df["sns_min"] / 60
df["messenger_hr"]      = df["messenger_min"] / 60
df["video_meeting_hr"]  = df["video_meeting_min"] / 60

# 디지털
df["co2e_digital"] = (
    df["youtube_hr"]*K_STREAMING_PER_HR +
    df["streaming_hr"]*K_STREAMING_PER_HR +
    df["sns_hr"]*K_SNS_PER_HR +
    df["messenger_hr"]*K_MSG_PER_HR +
    df["video_meeting_hr"]*K_MEET_PER_HR +
    (df["mobile_data_mb"]/1024.0)*K_MOBILE_PER_GB
)

# 이동
df["co2e_commute"] = df.apply(
    lambda r: r["commute_km"] * VEH_COEF.get(str(r["commute_mode"]).lower(), 0.0), axis=1
)

# 소비/식
df["co2e_consumption"] = (
    df["pet_bottles"]*K_PET +
    df["disposable_cups"]*K_CUP +
    df["delivery_used"].apply(lambda x: K_DELIVERY if str(x).lower() in ["yes","y","예","맞음","했다","사용"] else 0)
)
df["co2e_meal"] = df["lunch_type"].apply(
    lambda x: LUNCH_COEF.get(str(x).lower(), 1.2)  # 기본값: 혼합식
)

df["co2e_total"] = df["co2e_digital"] + df["co2e_commute"] + df["co2e_consumption"] + df["co2e_meal"]

# ---------------------------
# 필터
# ---------------------------
with st.sidebar:
    st.header("필터")
    # 날짜
    if df["date"].notna().any():
        dmin, dmax = pd.to_datetime(df["date"], errors="coerce").min(), pd.to_datetime(df["date"], errors="coerce").max()
        dr = st.date_input("날짜 범위", value=[dmin, dmax] if pd.notna(dmin) and pd.notna(dmax) else [])
    else:
        dr = []
    # 학급/팀
    grades = st.multiselect("학년", sorted([g for g in df["grade"].astype(str).unique() if g]))
    classes = st.multiselect("반", sorted([c for c in df["class"].astype(str).unique() if c]))
    teams = st.multiselect("팀/모둠", sorted([t for t in df["team"].astype(str).unique() if t]))
    show_raw = st.checkbox("원시 데이터 미리보기", value=False)

f = df.copy()
if len(dr) == 2:
    f = f[(pd.to_datetime(f["date"]) >= pd.to_datetime(dr[0])) & (pd.to_datetime(f["date"]) <= pd.to_datetime(dr[1]))]
if grades:
    f = f[f["grade"].astype(str).isin(grades)]
if classes:
    f = f[f["class"].astype(str).isin(classes)]
if teams:
    f = f[f["team"].astype(str).isin(teams)]

# ---------------------------
# KPI & 시각화
# ---------------------------
st.subheader("핵심 지표")
k1, k2, k3, k4 = st.columns(4)
k1.metric("총 CO₂e(kg)", f"{f['co2e_total'].sum():.2f}")
k2.metric("1인당 평균(kg)", f"{f.groupby('anon_id')['co2e_total'].sum().mean() if 'anon_id' in f.columns and len(f)>0 else 0:.2f}")
k3.metric("디지털 비중(%)", f"{(f['co2e_digital'].sum()/f['co2e_total'].sum()*100 if f['co2e_total'].sum()>0 else 0):.1f}")
k4.metric("응답 수", f"{len(f):,}")

st.subheader("항목별 총량(kg)")
st.bar_chart(f[["co2e_digital","co2e_commute","co2e_consumption","co2e_meal"]].sum())

if "date" in f.columns and f["date"].notna().any():
    st.subheader("일자별 추세")
    ts = f.groupby("date")[["co2e_total","co2e_digital"]].sum().sort_index()
    st.line_chart(ts)

st.subheader("팀/모둠 랭킹 (기간 합계, 낮을수록 우수)")
if "team" in f.columns and f["team"].astype(str).str.len().gt(0).any():
    rank = f.groupby("team")[["co2e_total","co2e_digital","co2e_commute","co2e_consumption","co2e_meal"]].sum().sort_values("co2e_total")
    st.dataframe(rank)
else:
    st.info("팀/모둠 컬럼이 매핑되지 않았습니다. 사이드바에서 팀 컬럼을 선택하세요.")

if show_raw:
    st.divider()
    st.subheader("원시 데이터")
    st.dataframe(df_raw)
    st.caption("컬럼명이 설문 문항 그대로 표시됩니다. 사이드바에서 매핑을 조정해 보세요.")

st.caption("※ 모든 계수는 교육용 추정치입니다. 상대 비교와 감축 추세 파악에 중점을 둡니다.")
