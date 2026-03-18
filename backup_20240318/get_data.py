import requests
import pandas as pd
import time

# =================設定區=================
# 請填入你的 ID 和 Secret
CLIENT_ID = 'u11216031-bc7bb8bf-ed67-4bc6'
CLIENT_SECRET = '50ced1f4-73d3-462c-ba09-4eebae7e9d4a'


AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
BASE_HEADERS = {"accept": "application/json"}

STATION_URL = "https://tdx.transportdata.tw/api/basic/v2/Rail/TRA/Station"
LINE_URL = "https://tdx.transportdata.tw/api/basic/v2/Rail/TRA/StationOfLine"

OUT_STATIONS = "tra_eastern_mainline_EL_stations.csv"
OUT_SEGMENTS = "tra_eastern_mainline_EL_segments.csv"

TARGET_LINE_ID = "EL"  # ✅ 東部幹線（你印出的起訖站：八堵→臺東）

# token 快取
_token_cache = {"token": None, "expires_at": 0}


def get_auth_token() -> str:
    """取得 TDX access token（含快取）。"""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 30:
        return _token_cache["token"]

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "缺少環境變數：TDX_CLIENT_ID / TDX_CLIENT_SECRET。\n"
            "請先設定環境變數後再執行。"
        )

    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    r = requests.post(AUTH_URL, data=data, headers=BASE_HEADERS, timeout=30)
    r.raise_for_status()
    payload = r.json()

    token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 3600))
    if not token:
        raise RuntimeError(f"取 token 失敗：{payload}")

    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expires_in
    return token


def request_with_retry(method: str, url: str, headers: dict, params: dict | None = None, max_retries: int = 6):
    """
    對 429/5xx 做重試（含退避）；其他錯誤直接 raise。
    """
    for attempt in range(max_retries):
        r = requests.request(method, url, headers=headers, params=params, timeout=30)

        if r.status_code in (429, 500, 502, 503, 504):
            # 退避：1,2,4,8,16,20...
            sleep_s = min(2 ** attempt, 20)
            reset = r.headers.get("ratelimit-reset") or r.headers.get("x-ratelimit-reset")
            msg = f"⚠️ {r.status_code}，{sleep_s}s 後重試：{url}"
            if reset:
                msg += f"（ratelimit-reset={reset}）"
            print(msg)
            time.sleep(sleep_s)
            continue

        r.raise_for_status()
        return r

    raise RuntimeError(f"重試仍失敗：{url}")


def fetch_all_by_paging(url: str, headers: dict, top: int = 1000) -> list:
    """用 $top/$skip 自動分頁抓取所有資料。"""
    all_rows = []
    skip = 0
    while True:
        params = {"$format": "JSON", "$top": top, "$skip": skip}
        r = request_with_retry("GET", url, headers=headers, params=params)
        chunk = r.json()

        if not isinstance(chunk, list):
            raise RuntimeError(f"回傳不是 list：{chunk}")

        if not chunk:
            break

        all_rows.extend(chunk)
        skip += top

    return all_rows


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """計算兩點距離（km）。"""
    # 防呆
    if any(v is None for v in [lat1, lon1, lat2, lon2]):
        return float("nan")

    R = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def main():
    token = get_auth_token()
    headers = {**BASE_HEADERS, "authorization": f"Bearer {token}"}

    # ========== Step 1：抓車站座標 ==========
    print("Step 1: 下載車站座標資料...")
    stations = fetch_all_by_paging(STATION_URL, headers=headers, top=1000)

    coord_map = {}
    for s in stations:
        sid = s.get("StationID")
        name = (s.get("StationName") or {}).get("Zh_tw")
        pos = s.get("StationPosition") or {}
        lat = pos.get("PositionLat")
        lon = pos.get("PositionLon")

        if not sid or name is None or lat is None or lon is None:
            continue

        coord_map[sid] = {"StationName": name, "Lat": float(lat), "Lon": float(lon)}

    print(f"車站座標筆數：{len(coord_map)}")

    # ========== Step 2：抓路線站序（只取 EL） ==========
    print("Step 2: 下載路線結構資料...")
    lines = fetch_all_by_paging(LINE_URL, headers=headers, top=1000)

    el_line = None
    for line in lines:
        if line.get("LineID") == TARGET_LINE_ID:
            el_line = line
            break

    if not el_line:
        raise RuntimeError(f"找不到 LineID={TARGET_LINE_ID}，請確認 StationOfLine 是否有此代碼。")

    # 建立 EL 車站表
    final_rows = []
    missing_coord = []

    for st in (el_line.get("Stations") or []):
        s_id = st.get("StationID")
        seq = st.get("Sequence")
        traveled = st.get("TraveledDistance")
        name_from_line = st.get("StationName")

        if s_id is None or seq is None:
            continue

        cm = coord_map.get(s_id)
        if cm is None:
            missing_coord.append(s_id)

        final_rows.append({
            "LineID": TARGET_LINE_ID,
            "Sequence": int(seq),
            "TraveledDistance": traveled,
            "StationID": s_id,
            # 優先用 Station API 的中文站名（較一致）
            "StationName": (cm or {}).get("StationName", name_from_line),
            "Lat": (cm or {}).get("Lat"),
            "Lon": (cm or {}).get("Lon"),
        })

    df = pd.DataFrame(final_rows).sort_values(["Sequence"]).reset_index(drop=True)

    # ========== 驗收檢查 ==========
    print("=== 驗收檢查（EL 東部幹線）===")
    print("站數：", len(df))
    if len(df) > 0:
        print("起點站：", df.iloc[0]["StationName"], " / 終點站：", df.iloc[-1]["StationName"])

        # Sequence 連續檢查
        seq_list = df["Sequence"].tolist()
        expected = list(range(seq_list[0], seq_list[0] + len(seq_list)))
        if seq_list != expected:
            missing_seq = sorted(set(expected) - set(seq_list))
            print("⚠️ Sequence 不連續，缺：", missing_seq[:50])
        else:
            print("Sequence 連續 ✅")

    missing_coord_unique = sorted(set(missing_coord))
    print("缺座標站數：", len(missing_coord_unique))
    if missing_coord_unique:
        print("缺座標 StationID（前 30 個）：", missing_coord_unique[:30])

    # ========== 輸出 stations.csv ==========
    df.to_csv(OUT_STATIONS, index=False, encoding="utf-8-sig")
    print(f"✅ 已輸出：{OUT_STATIONS}")

    # ========== 產出 segments.csv（相鄰站路段） ==========
    # 用 traveled distance 差分做路段長度；如果 traveled 缺，用 haversine 當備援
    segments = []
    for i in range(len(df) - 1):
        a = df.iloc[i]
        b = df.iloc[i + 1]

        # 路段長度（km）：優先用 TraveledDistance 差
        seg_len = float("nan")
        if pd.notna(a["TraveledDistance"]) and pd.notna(b["TraveledDistance"]):
            try:
                seg_len = float(b["TraveledDistance"]) - float(a["TraveledDistance"])
            except Exception:
                seg_len = float("nan")

        # 備援：用座標估算距離
        if not (isinstance(seg_len, float) and seg_len >= 0):
            seg_len = haversine_km(a["Lat"], a["Lon"], b["Lat"], b["Lon"])

        # midpoint（路段中心點）
        mid_lat = float("nan")
        mid_lon = float("nan")
        if pd.notna(a["Lat"]) and pd.notna(a["Lon"]) and pd.notna(b["Lat"]) and pd.notna(b["Lon"]):
            mid_lat = (float(a["Lat"]) + float(b["Lat"])) / 2
            mid_lon = (float(a["Lon"]) + float(b["Lon"])) / 2

        segments.append({
            "LineID": TARGET_LINE_ID,
            "FromSequence": int(a["Sequence"]),
            "ToSequence": int(b["Sequence"]),
            "FromStationID": a["StationID"],
            "FromStationName": a["StationName"],
            "ToStationID": b["StationID"],
            "ToStationName": b["StationName"],
            "SegmentLengthKM": seg_len,
            "MidLat": mid_lat,
            "MidLon": mid_lon,
        })

    seg_df = pd.DataFrame(segments)
    seg_df.to_csv(OUT_SEGMENTS, index=False, encoding="utf-8-sig")
    print(f"✅ 已輸出：{OUT_SEGMENTS}")

    print("\n--- 預覽（stations head）---")
    print(df.head(10))
    print("\n--- 預覽（segments head）---")
    print(seg_df.head(10))


if __name__ == "__main__":
    main()