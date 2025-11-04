# app.py
import streamlit as st
import pandas as pd
import numpy as np
import json, gspread
from oauth2client.service_account import ServiceAccountCredentials
st.set_page_config(page_title="디지털 탄소발자국 대시보드", layout="wide")

@st.cache_resource
def gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds_json = st.secrets["GSHEETS_CREDENTIALS"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds_json), scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_data():
    # ✅ Google Sheets에서 직접 읽기
    sh = gsheet_client().open_by_key(st.secrets["SHEET_ID"]).worksheet(st.secrets.get("SHEET_NAME", "Form Responses 1"))
    rows = sh.get_all_records()  # 1행 헤더 기준
    df = pd.DataFrame(rows)
    # date 컬럼 정제(없어도 에러 안 나게)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    elif "Timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    else:
        df["date"] = pd.NaT
    return df

def compute_co2e(df):
    # 교육용 간이 계수
    k_streaming_per_hr = 0.08
    k_sns_per_hr = 0.04
    k_msg_per_hr = 0.04
    k_video_meeting_per_hr = 0.15
    k_mobile_data_per_gb = 0.05

    k_subway_per_km = 0.04
    k_bus_per_km = 0.08
    k_car_per_km = 0.18
    k_walk_bike_per_km = 0.0
    vehicle_coef = {
        "subway": k_subway_per_km,
        "bus": k_bus_per_km,
        "car": k_car_per_km,
        "carpool": k_car_per_km/2,  # 단순 가정
        "walk": k_walk_bike_per_km,
        "bike": k_walk_bike_per_km,
    }

    k_pet = 0.08
    k_cup = 0.03
    k_delivery = 0.5

    df = df.copy()
    # 분→시간
    for c in ["youtube_min","streaming_min","sns_min","messenger_min","video_meeting_min"]:
        if c in df.columns:
            df[c.replace("_min","_hr")] = df[c].fillna(0)/60.0

    df["co2e_digital"] = (
        df.get("streaming_hr",0)*k_streaming_per_hr
        + df.get("youtube_hr",0)*k_streaming_per_hr
        + df.get("sns_hr",0)*k_sns_per_hr
        + df.get("messenger_hr",0)*k_msg_per_hr
        + df.get("video_meeting_hr",0)*k_video_meeting_per_hr
        + (df.get("mobile_data_mb",0)/1024.0)*k_mobile_data_per_gb
    )

    df["co2e_commute"] = df.apply(
        lambda r: r.get("commute_km",0) * vehicle_coef.get(str(r.get("commute_mode","")).lower(), 0.0),
        axis=1
    )

    df["co2e_consumption"] = (
        df.get("pet_bottles",0)*k_pet
        + df.get("disposable_cups",0)*k_cup
        + (df.get("delivery_used","no").astype(str).str.lower().eq("yes")).astype(int)*k_delivery
    )

    df["co2e_total"] = df["co2e_digital"] + df["co2e_commute"] + df["co2e_consumption"]
    return df

st.title("우리 반 디지털 탄소발자국 대시보드")

df_raw = load_data()
df = compute_co2e(df_raw)

# 사이드바 필터
with st.sidebar:
    st.header("필터")
    grades = st.multiselect("학년", sorted(df["grade"].astype(str).unique()), default=None)
    classes = st.multiselect("반", sorted(df["class"].astype(str).unique()), default=None)
    teams = st.multiselect("팀", sorted(df["team"].astype(str).unique()), default=None)
    date_range = st.date_input("날짜 범위", [])
    filtered = df.copy()
    if grades: filtered = filtered[filtered["grade"].astype(str).isin(grades)]
    if classes: filtered = filtered[filtered["class"].astype(str).isin(classes)]
    if teams: filtered = filtered[filtered["team"].astype(str).isin(teams)]
    if len(date_range) == 2:
        d0, d1 = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        filtered = filtered[(filtered["date"]>=d0)&(filtered["date"]<=d1)]

# KPI
col1, col2, col3, col4 = st.columns(4)
col1.metric("총 CO₂e(kg)", f"{filtered['co2e_total'].sum():.2f}")
col2.metric("1인당 평균(kg)", f"{filtered.groupby('anon_id')['co2e_total'].sum().mean():.2f}")
col3.metric("디지털 비중(%)", f"{(filtered['co2e_digital'].sum()/filtered['co2e_total'].sum()*100 if filtered['co2e_total'].sum()>0 else 0):.1f}")
col4.metric("기록 수(행)", f"{len(filtered):,}")

st.subheader("항목별 총량")
st.bar_chart(filtered[["co2e_digital","co2e_commute","co2e_consumption"]].sum())

st.subheader("요일/추세 보기")
ts = filtered.groupby("date")[["co2e_total","co2e_digital"]].sum()
st.line_chart(ts)

st.subheader("팀 랭킹 (기간 합계)")
rank = filtered.groupby("team")[["co2e_total","co2e_digital","co2e_commute","co2e_consumption"]].sum().sort_values("co2e_total")
st.dataframe(rank)

st.caption("※ 계수는 수업용 추정치입니다. 동일 계수를 유지해 상대 비교와 감축 추세를 보는 데 초점을 둡니다.")
