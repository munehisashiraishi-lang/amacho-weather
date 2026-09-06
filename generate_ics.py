import re
import uuid
from datetime import datetime, timedelta, timezone
from icalendar import Calendar, Event
import requests

OUTPUT_FILE = "amacho.ics"
JMA_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/320000.json"

# 気象庁 天気コード -> テキスト変換マップ
JMA_WEATHER_CODES = {
    "100": "晴れ",
    "101": "晴れ時々くもり",
    "102": "晴れ一時雨",
    "103": "晴れ時々雨",
    "104": "晴れ一時雪",
    "105": "晴れ時々雪",
    "110": "晴れ後時々くもり",
    "111": "晴れ後くもり",
    "112": "晴れ後一時雨",
    "113": "晴れ後時々雨",
    "114": "晴れ後雨",
    "200": "くもり",
    "201": "くもり時々晴れ",
    "202": "くもり一時雨",
    "203": "くもり時々雨",
    "204": "くもり一時雪",
    "205": "くもり時々雪",
    "210": "くもり後時々晴れ",
    "211": "くもり後晴れ",
    "212": "くもり後一時雨",
    "213": "くもり後時々雨",
    "214": "くもり後雨",
    "300": "雨",
    "301": "雨時々晴れ",
    "302": "雨時々くもり",
    "303": "雨時々雪",
    "311": "雨後晴れ",
    "313": "雨後くもり",
    "400": "雪",
}


def fetch_weather():
    response = requests.get(JMA_URL)
    response.raise_for_status()
    return response.json()


def clean_text(text):
    if not text:
        return ""
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

    weather_by_date = {}

    # -------------------------------------------------------------
    # 1. 短期予報 (1〜3日目の詳細テキスト)
    # -------------------------------------------------------------
    if len(data) > 0:
        time_series = data[0].get("timeSeries", [])
        if len(time_series) > 0:
            ts_w = time_series[0]
            dates = ts_w.get("timeDefines", [])
            for area in ts_w.get("areas", []):
                # 隠岐エリア（320020）
                if area.get("area", {}).get("code") in [
                    "320020",
                    "320000",
                ]:
                    for i, t_str in enumerate(dates):
                        d_str = (
                            datetime.fromisoformat(t_str).date().isoformat()
                        )
                        if d_str not in weather_by_date:
                            weather_by_date[d_str] = {}
                        if "weather" not in weather_by_date[d_str] and i < len(
                            area.get("weathers", [])
                        ):
                            weather_by_date[d_str]["weather"] = clean_text(
                                area["weathers"][i]
                            )

        # 降水確率
        if len(time_series) > 1:
            ts_p = time_series[1]
            dates = ts_p.get("timeDefines", [])
            for area in ts_p.get("areas", []):
                if area.get("area", {}).get("code") in [
                    "320020",
                    "320000",
                ]:
                    for i, t_str in enumerate(dates):
                        d_str = (
                            datetime.fromisoformat(t_str).date().isoformat()
                        )
                        pops = area.get("pops", [])
                        if i < len(pops) and pops[i]:
                            if d_str in weather_by_date:
                                cur = weather_by_date[d_str].get("pop")
                                if cur is None or int(pops[i]) > int(cur):
                                    weather_by_date[d_str]["pop"] = pops[i]

    # -------------------------------------------------------------
    # 2. 週間予報 (3〜7日目の補完)
    # -------------------------------------------------------------
    if len(data) > 1:
        time_series_w = data[1].get("timeSeries", [])

        # 週間天気コード
        if len(time_series_w) > 0:
            ts_w2 = time_series_w[0]
            dates = ts_w2.get("timeDefines", [])
            for area in ts_w2.get("areas", []):
                # 週間予報ではエリアコードが 320000 または 320020 で格納される
                pops = area.get("pops", [])
                codes = area.get("weatherCodes", [])
                for i, t_str in enumerate(dates):
                    d_str = datetime.fromisoformat(t_str).date().isoformat()
                    if d_str not in weather_by_date:
                        weather_by_date[d_str] = {}

                    # 天気未登録の日付をコード変換で充填
                    if "weather" not in weather_by_date[d_str]:
                        w_code = codes[i] if i < len(codes) else ""
                        weather_by_date[d_str]["weather"] = (
                            JMA_WEATHER_CODES.get(w_code, "くもり")
                        )

                    if (
                        "pop" not in weather_by_date[d_str]
                        and i < len(pops)
                        and pops[i]
                    ):
                        weather_by_date[d_str]["pop"] = pops[i]

        # 週間気温（西郷 / 隠岐）
        if len(time_series_w) > 1:
            ts_temp = time_series_w[1]
            dates = ts_temp.get("timeDefines", [])
            for area in ts_temp.get("areas", []):
                # 西郷地点(68006) または 隠岐/島根(320020/320000)
                temps_min = area.get("tempsMin", [])
                temps_max = area.get("tempsMax", [])
                for i, t_str in enumerate(dates):
                    d_str = datetime.fromisoformat(t_str).date().isoformat()
                    if d_str not in weather_by_date:
                        weather_by_date[d_str] = {}
                    if i < len(temps_min) and temps_min[i]:
                        weather_by_date[d_str]["min_temp"] = temps_min[i]
                    if i < len(temps_max) and temps_max[i]:
                        weather_by_date[d_str]["max_temp"] = temps_max[i]

    # -------------------------------------------------------------
    # 3. iCal生成
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
    print(f"合計 {len(weather_by_date)} 日分の予報を生成しました。")


if __name__ == "__main__":
    create_calendar()
