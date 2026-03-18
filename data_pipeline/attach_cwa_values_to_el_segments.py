import os
import requests
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========= 你要設定的地方 =========
CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"

RAIN_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
WX_URL   = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"

MAP_RAIN_CSV = "el_segments_to_rain_station.csv"
MAP_WX_CSV   = "el_segments_to_weather_station.csv"
OUT_CSV      = "el_segments_with_live_weather.csv"

# 若你那台電腦會 SSL 驗證失敗，保持 False
VERIFY_SSL = False
# =================================


def safe_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "" or s.lower() == "nan":
            return None
        v = float(s)
        # CWA 常見缺測代碼（如 -990 / -999）
        if v <= -90:
            return None
        return v
    except Exception:
        return None


def cwa_get_json(url: str):
    if not CWA_KEY:
        raise RuntimeError("缺少 CWA_KEY。請先設定環境變數 CWA_KEY 或在程式裡填入。")

    params = {"Authorization": CWA_KEY, "format": "JSON"}
    r = requests.get(url, params=params, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json()


def parse_rain_df(data: dict) -> pd.DataFrame:
    """把 O-A0002-001 轉成：StationId -> 即時雨量欄位"""
    stations = data.get("records", {}).get("Station", [])
    rows = []
    for s in stations:
        sid = s.get("StationId")
        name = s.get("StationName")
        obs_time = (s.get("ObsTime") or {}).get("DateTime")

        rf = s.get("RainfallElement") or {}
        now  = safe_float(((rf.get("Now") or {}).get("Precipitation")))
        p10  = safe_float(((rf.get("Past10Min") or {}).get("Precipitation")))
        p1h  = safe_float(((rf.get("Past1hr") or {}).get("Precipitation")))
        p3h  = safe_float(((rf.get("Past3hr") or {}).get("Precipitation")))
        p6h  = safe_float(((rf.get("Past6Hr") or {}).get("Precipitation")))
        p24  = safe_float(((rf.get("Past24hr") or {}).get("Precipitation")))

        if not sid:
            continue

        rows.append({
            "StationId": sid,
            "RainStationName": name,
            "RainObsTime": obs_time,
            "RainNow": now,
            "RainPast10Min": p10,
            "RainPast1Hr": p1h,
            "RainPast3Hr": p3h,
            "RainPast6Hr": p6h,
            "RainPast24Hr": p24,
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["StationId"])
    return df


def parse_wx_df(data: dict) -> pd.DataFrame:
    """把 O-A0003-001 轉成：StationId -> 即時風速/陣風/能見度/溫度等（常用）"""
    stations = data.get("records", {}).get("Station", [])
    rows = []
    for s in stations:
        sid = s.get("StationId")
        name = s.get("StationName")
        obs_time = (s.get("ObsTime") or {}).get("DateTime")

        we = s.get("WeatherElement") or {}
        wind_speed = safe_float(we.get("WindSpeed"))
        wind_dir   = safe_float(we.get("WindDirection"))
        temp       = safe_float(we.get("AirTemperature"))
        rh         = safe_float(we.get("RelativeHumidity"))
        vis        = we.get("VisibilityDescription")

        gust = (we.get("GustInfo") or {}).get("PeakGustSpeed")
        gust_speed = safe_float(gust)

        if not sid:
            continue

        rows.append({
            "StationId": sid,
            "WxStationName": name,
            "WxObsTime": obs_time,
            "WindSpeed": wind_speed,
            "WindDirection": wind_dir,
            "PeakGustSpeed": gust_speed,
            "AirTemperature": temp,
            "RelativeHumidity": rh,
            "VisibilityDescription": vis,
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["StationId"])
    return df


def main():
    # 1) 讀入兩張對應表
    map_rain = pd.read_csv(MAP_RAIN_CSV, encoding="utf-8-sig")
    map_wx   = pd.read_csv(MAP_WX_CSV, encoding="utf-8-sig")

    # 2) 抓即時雨量
    print("下載即時雨量（O-A0002-001）...")
    rain_json = cwa_get_json(RAIN_URL)
    rain_df = parse_rain_df(rain_json)
    print(f"雨量站即時筆數：{len(rain_df)}")

    # 3) 抓即時綜觀氣象（風速等）
    print("下載即時綜觀氣象（O-A0003-001）...")
    wx_json = cwa_get_json(WX_URL)
    wx_df = parse_wx_df(wx_json)
    print(f"綜觀站即時筆數：{len(wx_df)}")

    # 4) 把雨量值掛回路段（用 Nearest_RAIN_StationId）
    if "Nearest_RAIN_StationId" not in map_rain.columns:
        raise RuntimeError("map_rain 缺少欄位 Nearest_RAIN_StationId（請確認你輸出的 csv 欄位名）")

    seg_rain = map_rain.merge(
        rain_df,
        how="left",
        left_on="Nearest_RAIN_StationId",
        right_on="StationId"
    ).drop(columns=["StationId"], errors="ignore")

    # 5) 把氣象值掛回路段（用 Nearest_WEATHER_StationId）
    if "Nearest_WEATHER_StationId" not in map_wx.columns:
        raise RuntimeError("map_wx 缺少欄位 Nearest_WEATHER_StationId（請確認你輸出的 csv 欄位名）")

    seg_wx = map_wx.merge(
        wx_df,
        how="left",
        left_on="Nearest_WEATHER_StationId",
        right_on="StationId"
    ).drop(columns=["StationId"], errors="ignore")

    # 6) 合併成一張總表
    # 兩張對應表其實是同一份 segments，只是附了不同最近站資訊
    # 用 From/To StationID 這些欄位來合併最穩（若你欄位名不同，可改成用 FromSequence/ToSequence）
    key_candidates = ["LineID", "FromStationID", "ToStationID", "FromSequence", "ToSequence"]
    merge_keys = [k for k in key_candidates if k in seg_rain.columns and k in seg_wx.columns]
    if not merge_keys:
        raise RuntimeError("找不到可用的合併鍵（請確認 segments 欄位，例如 FromStationID/ToStationID）")

    final = seg_rain.merge(seg_wx, how="inner", on=merge_keys, suffixes=("_rainMap", "_wxMap"))

    final.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print("--------------------------------------------------")
    print(f"✅ 完成！已輸出：{OUT_CSV}")

    # 7) 簡單驗收：看前 8 筆路段有沒有掛到值
    cols_preview = []
    for c in [
        "FromStationName", "ToStationName",
        "Nearest_RAIN_StationName", "DistTo_RAIN_KM",
        "RainPast1Hr", "RainPast10Min",
        "Nearest_WEATHER_StationName", "DistTo_WEATHER_KM",
        "WindSpeed", "PeakGustSpeed"
    ]:
        if c in final.columns:
            cols_preview.append(c)

    print("\n--- 預覽（前 8 筆）---")
    print(final[cols_preview].head(8))

if __name__ == "__main__":
    main()