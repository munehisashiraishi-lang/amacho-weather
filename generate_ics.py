import re
import uuid
from datetime import datetime, timedelta, timezone
from icalendar import Calendar, Event
import requests

OUTPUT_FILE = "amacho.ics"
JMA_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/320000.json"


def fetch_weather():
    response = requests.get(JMA_URL)
    response.raise_for_status()
    return response.json()


def clean_text(text):
    if not text:
        return ""
    # 空白の乱れを綺麗に整形
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def create_calendar():
    data = fetch_weather()
    cal = Calendar()
    cal.add("prodid", "-//Amacho Weather Calendar//NONSGML v1.0//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "海士町 週間天気予報")
    cal.add("x-wr-timezone", "Asia/Tokyo")

    # 日付ごとのデータ格納用辞書
    weather_by_date = {}

    # -------------------------------------------------------------
    # 1. 短期予報 (今日・明日・明後日の詳細データ)
    # -------------------------------------------------------------
    if len(data) > 0:
        time_series = data[0].get("timeSeries", [])

        # 天気
        if len(time_series) > 0:
            ts_w = time_series[0]
            dates = ts_w.get("timeDefines", [])
            for area in ts_w.get("areas", []):
                if area.get("area", {}).get("code") == "320020":  # 隠岐エリア
                    for i, t_str in enumerate(dates):
                        d_str = (
                            datetime.fromisoformat(t_str).date().isoformat()
                        )
                        if d_str not in weather_by_date:
                            weather_by_date[d_str] = {}
                        weather_by_date[d_str]["weather"] = clean_text(
                            area["weathers"][i]
                        )

        # 降水確率 (短期)
        if len(time_series) > 1:
            ts_p = time_series[1]
            dates = ts_p.get("timeDefines", [])
            for area in ts_p.get("areas", []):
                if area.get("area", {}).get("code") == "320020":
                    for i, t_str in enumerate(dates):
                        d_str = (
                            datetime.fromisoformat(t_str).date().isoformat()
                        )
                        pop_val = area["pops"][i]
                        if d_str in weather_by_date and pop_val:
                            cur = weather_by_date[d_str].get("pop")
                            if cur is None or int(pop_val) > int(cur):
                                weather_by_date[d_str]["pop"] = pop_val

    # -------------------------------------------------------------
    # 2. 週間予報 (3日目〜7日目のデータ)
    # -------------------------------------------------------------
    if len(data) > 1:
        time_series_w = data[1].get("timeSeries", [])

        # 週間天気 (コードから変換、またはテロップ)
        if len(time_series_w) > 0:
            ts_w2 = time_series_w[0]
            dates = ts_w2.get("timeDefines", [])
            for area in ts_w2.get("areas", []):
                if area.get("area", {}).get("code") == "320020":
                    pops = area.get("pops", [])
                    weather_codes = area.get("weatherCodes", [])

                    # 天気コード変換マップ（主要な天気）
                    code_map = {
                        "100": "晴れ",
                        "101": "晴れ時々くもり",
                        "200": "くもり",
                        "201": "くもり時々晴れ",
                        "300": "雨",
                        "301": "雨時々晴れ",
                    }

                    for i, t_str in enumerate(dates):
                        d_str = (
                            datetime.fromisoformat(t_str).date().isoformat()
                        )
                        if d_str not in weather_by_date:
                            weather_by_date[d_str] = {}

                        # 短期データにない後半日程の天気を補充
                        if "weather" not in weather_by_date[d_str]:
                            w_code = (
                                weather_codes[i]
                                if i < len(weather_codes)
                                else ""
                            )
                            weather_by_date[d_str]["weather"] = code_map.get(
                                w_code, "くもり"
                            )

                        # 週間降水確率の補充
                        if (
                            "pop" not in weather_by_date[d_str]
                            and i < len(pops)
                            and pops[i]
                        ):
                            weather_by_date[d_str]["pop"] = pops[i]

        # 週間気温（最低・最高）
        if len(time_series_w) > 1:
            ts_temp = time_series_w[1]
            dates = ts_temp.get("timeDefines", [])
            for area in ts_temp.get("areas", []):
                if area.get("area", {}).get("code") in ["320020", "68006"]:
                    temps_min = area.get("tempsMin", [])
                    temps_max = area.get("tempsMax", [])
                    for i, t_str in enumerate(dates):
                        d_str = (
                            datetime.fromisoformat(t_str).date().isoformat()
                        )
                        if d_str not in weather_by_date:
                            weather_by_date[d_str] = {}
                        if i < len(temps_min) and temps_min[i]:
                            weather_by_date[d_str]["min_temp"] = temps_min[i]
                        if i < len(temps_max) and temps_max[i]:
                            weather_by_date[d_str]["max_temp"] = temps_max[i]

    # -------------------------------------------------------------
    # 3. iCalイベント出力（7日分生成）
    # -------------------------------------------------------------
    for d_str, info in sorted(weather_by_date.items()):
        if "weather" not in info:
            continue

        target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
        weather_text = info["weather"]
        pop_text = f"{info['pop']}%" if "pop" in info else "---"

        min_t = info.get("min_temp", "-")
        max_t = info.get("max_temp", "-")

        temp_str = ""
        if min_t != "-" or max_t != "-":
            temp_str = f" {max_t}℃/{min_t}℃"

        event = Event()
        event.add("uid", f"{d_str}-weather@amacho-weather")
        event.add("dtstart", target_date)
        event.add("dtend", target_date + timedelta(days=1))

        # 松江版と同様の形式でタイトル生成
        event.add("summary", f"海士町: {weather_text}{temp_str}")

        desc = (
            f"【海士町（隠岐）の天気予報】\n"
            f"■ 天気：{weather_text}\n"
            f"■ 降水確率：{pop_text}\n"
            f"■ 最高/最低気温：{max_t}℃ / {min_t}℃\n\n"
            f"発表元：気象庁"
        )
        event.add("description", desc)
        event.add("dtstamp", datetime.now(timezone.utc))

        cal.add_component(event)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())
    print("1週間分の天気予報カレンダーを正常に作成しました。")


if __name__ == "__main__":
    create_calendar()
