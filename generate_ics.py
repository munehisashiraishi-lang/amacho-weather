import uuid
from datetime import datetime, timedelta, timezone
from icalendar import Calendar, Event
import requests

OUTPUT_FILE = "amacho.ics"
# 島根県の天気予報データJSON
JMA_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/320000.json"


def fetch_weather():
    response = requests.get(JMA_URL)
    response.raise_for_status()
    return response.json()


def create_calendar():
    data = fetch_weather()
    cal = Calendar()
    cal.add("prodid", "-//Amacho Weather Calendar//NONSGML v1.0//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "海士町 天気予報")
    cal.add("x-wr-timezone", "Asia/Tokyo")

    # 隠岐地区（320020）の予報データを抽出
    time_series = data[0]["timeSeries"]

    # 1. 天気テキストの抽出
    area_weather = None
    for ts in time_series:
        if "weathers" in ts["areas"][0]:
            for area in ts["areas"]:
                if area["area"]["code"] == "320020":  # 隠岐エリア
                    area_weather = area
                    time_defines = ts["timeDefines"]
                    break

    if not area_weather:
        print("隠岐エリアのデータが見つかりませんでした。")
        return

    # カレンダーイベントの生成
    for i, time_str in enumerate(time_defines):
        # 日付パース
        dt = datetime.fromisoformat(time_str)
        target_date = dt.date()
        weather_text = area_weather["weathers"][i].replace(" ", " ")

        event = Event()
        # 毎日同じUIDにならないよう固定ハッシュ形式（Googleカレンダーの重複防止）
        event.add("uid", f"{target_date}-weather@amacho-weather")
        event.add("dtstart", target_date)
        event.add("dtend", target_date + timedelta(days=1))
        event.add("summary", f"海士町: {weather_text}")
        event.add(
            "description",
            f"【海士町（隠岐）の天気予報】\n天気: {weather_text}\n発表元: 気象庁",
        )
        event.add("dtstamp", datetime.now(timezone.utc))

        cal.add_component(event)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())
    print(f"Successfully generated {OUTPUT_FILE}")


if __name__ == "__main__":
    create_calendar()
