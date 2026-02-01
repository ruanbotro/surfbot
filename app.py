from __future__ import annotations

import os
import urllib.request
from datetime import datetime, timezone

from flask import Flask, jsonify, Response

app = Flask(__name__)

JACKSONVILLE = {
    "name": "Jacksonville, FL",
    "latitude": 30.3322,
    "longitude": -81.6557,
}

NDBC_STATION = {
    "id": "41012",
    "name": "St. Augustine, FL (NDBC 41012)",
}

SURF_THRESHOLDS = {
    "min_wave_height_m": 0.8,
    "max_wave_height_m": 2.5,
    "min_wave_period_s": 6,
    "max_wind_speed_mps": 10,
}


def build_marine_url() -> str:
    return (
        "https://www.ndbc.noaa.gov/data/realtime2/"
        f"{NDBC_STATION['id']}.txt"
    )


def parse_ndbc_realtime(data: str) -> dict:
    lines = [line.strip() for line in data.splitlines() if line.strip()]
    header_line = next(
        (line for line in lines if line.startswith("#")), None
    )
    if header_line is None:
        raise ValueError("Missing header row in NDBC response.")

    header = header_line.lstrip("#").split()
    values_line = next(
        (line for line in lines if not line.startswith("#")), None
    )
    if values_line is None:
        raise ValueError("Missing data row in NDBC response.")

    values = values_line.split()
    columns = {name: index for index, name in enumerate(header)}

    def read_value(column: str) -> str:
        index = columns.get(column)
        if index is None or index >= len(values):
            raise ValueError(f"Missing {column} field in NDBC response.")
        return values[index]

    year = int(read_value("YY"))
    year += 2000 if year < 70 else 1900
    month = int(read_value("MM"))
    day = int(read_value("DD"))
    hour = int(read_value("hh"))
    minute = int(read_value("mm"))
    timestamp = datetime(
        year, month, day, hour, minute, tzinfo=timezone.utc
    ).isoformat()

    wave_height_raw = read_value("WVHT")
    wind_speed_raw = read_value("WSPD")
    period_raw = read_value("DPD")
    if period_raw == "MM" and "APD" in columns:
        period_raw = read_value("APD")

    def parse_float(value: str) -> float:
        if value == "MM":
            raise ValueError("Missing measurement in NDBC response.")
        return float(value)

    return {
        "time": timestamp,
        "wave_height": parse_float(wave_height_raw),
        "wave_period": parse_float(period_raw),
        "wind_speed": parse_float(wind_speed_raw),
        "station": NDBC_STATION["name"],
    }


def fetch_marine_forecast() -> dict:
    marine_url = build_marine_url()
    request = urllib.request.Request(
        marine_url,
        headers={
            "User-Agent": "surfbot/1.0 (+https://www.ndbc.noaa.gov/)",
            "Accept": "text/plain",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return parse_ndbc_realtime(response.read().decode("utf-8"))


def assess_surf(wave_height: float, wave_period: float, wind_speed: float) -> dict:
    meets_wave_height = (
        SURF_THRESHOLDS["min_wave_height_m"]
        <= wave_height
        <= SURF_THRESHOLDS["max_wave_height_m"]
    )
    meets_wave_period = wave_period >= SURF_THRESHOLDS["min_wave_period_s"]
    meets_wind = wind_speed <= SURF_THRESHOLDS["max_wind_speed_mps"]

    good_surf = meets_wave_height and meets_wave_period and meets_wind
    reasons: list[str] = []

    if not meets_wave_height:
        reasons.append(
            "Wave height ({:.1f} m) should be between {} and {} m.".format(
                wave_height,
                SURF_THRESHOLDS["min_wave_height_m"],
                SURF_THRESHOLDS["max_wave_height_m"],
            )
        )
    if not meets_wave_period:
        reasons.append(
            "Wave period ({:.0f} s) should be at least {} s.".format(
                wave_period, SURF_THRESHOLDS["min_wave_period_s"]
            )
        )
    if not meets_wind:
        reasons.append(
            "Wind speed ({:.1f} m/s) should be below {} m/s.".format(
                wind_speed, SURF_THRESHOLDS["max_wind_speed_mps"]
            )
        )

    return {"good_surf": good_surf, "reasons": reasons}


@app.get("/")
def index() -> Response:
    return Response(
        """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Jacksonville Surf Dashboard</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: "Inter", system-ui, sans-serif;
      background: #0b1220;
      color: #f5f7ff;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: radial-gradient(circle at top, #1b2a44, #0b1220 65%);
    }
    .card {
      width: min(720px, 92vw);
      padding: 32px;
      border-radius: 20px;
      background: rgba(15, 23, 42, 0.85);
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
      display: grid;
      gap: 20px;
    }
    h1 {
      margin: 0;
      font-size: 2rem;
    }
    .status {
      padding: 16px 20px;
      border-radius: 16px;
      font-size: 1.4rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .status.good {
      background: rgba(16, 185, 129, 0.2);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #d1fae5;
    }
    .status.bad {
      background: rgba(248, 113, 113, 0.2);
      border: 1px solid rgba(248, 113, 113, 0.4);
      color: #fee2e2;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 16px;
    }
    .metric {
      padding: 14px 16px;
      background: rgba(30, 41, 59, 0.7);
      border-radius: 14px;
    }
    .metric span {
      display: block;
      font-size: 0.85rem;
      opacity: 0.7;
    }
    .metric strong {
      font-size: 1.2rem;
    }
    ul {
      margin: 0;
      padding-left: 20px;
      opacity: 0.85;
    }
    .footer {
      font-size: 0.85rem;
      opacity: 0.7;
    }
  </style>
</head>
<body>
  <main class=\"card\">
    <header>
      <h1>Jacksonville Surf Conditions</h1>
        <p>Latest buoy report near Jacksonville, FL.</p>
    </header>
    <section id=\"status\" class=\"status\">Loading latest surf report...</section>
    <section class=\"metrics\">
      <div class=\"metric\">
        <span>Wave Height</span>
        <strong id=\"wave-height\">--</strong>
      </div>
      <div class=\"metric\">
        <span>Wave Period</span>
        <strong id=\"wave-period\">--</strong>
      </div>
      <div class=\"metric\">
        <span>Wind Speed</span>
        <strong id=\"wind-speed\">--</strong>
      </div>
      <div class=\"metric\">
        <span>Data Time</span>
        <strong id=\"data-time\">--</strong>
      </div>
    </section>
    <section>
      <h2>Why this call?</h2>
      <ul id=\"reasons\">
        <li>Loading thresholds...</li>
      </ul>
    </section>
    <div class=\"footer\">Data source: NOAA NDBC buoy report.</div>
  </main>

  <script>
    async function loadSurf() {
      const statusEl = document.getElementById('status');
      const waveHeightEl = document.getElementById('wave-height');
      const wavePeriodEl = document.getElementById('wave-period');
      const windSpeedEl = document.getElementById('wind-speed');
      const dataTimeEl = document.getElementById('data-time');
      const reasonsEl = document.getElementById('reasons');

      try {
        const response = await fetch('/api/surf');
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || response.statusText);
        }

        statusEl.textContent = data.statusMessage;
        statusEl.classList.remove('good', 'bad');
        statusEl.classList.add(data.goodSurf ? 'good' : 'bad');

        waveHeightEl.textContent = `${data.waveHeight.toFixed(1)} m`;
        wavePeriodEl.textContent = `${data.wavePeriod.toFixed(0)} s`;
        windSpeedEl.textContent = `${data.windSpeed.toFixed(1)} m/s`;
        dataTimeEl.textContent = new Date(data.time).toLocaleString();

        reasonsEl.innerHTML = '';
        data.reasons.forEach((reason) => {
          const li = document.createElement('li');
          li.textContent = reason;
          reasonsEl.appendChild(li);
        });
      } catch (error) {
        statusEl.textContent = error.message;
        statusEl.classList.add('bad');
        reasonsEl.innerHTML = `<li>${error.message}</li>`;
      }
    }

    loadSurf();
  </script>
</body>
</html>""",
        mimetype="text/html",
    )


@app.get("/api/surf")
def api_surf() -> Response:
    try:
        payload = fetch_marine_forecast()

        wave_height = payload["wave_height"]
        wave_period = payload["wave_period"]
        wind_speed = payload["wind_speed"]

        assessment = assess_surf(wave_height, wave_period, wind_speed)

        status_message = (
            "Good surf right now — grab your board!"
            if assessment["good_surf"]
            else "Surf conditions are not great right now."
        )

        return jsonify(
            {
                "location": JACKSONVILLE["name"],
                "time": payload["time"],
                "waveHeight": wave_height,
                "wavePeriod": wave_period,
                "windSpeed": wind_speed,
                "goodSurf": assessment["good_surf"],
                "reasons": assessment["reasons"]
                or ["All key thresholds are within the preferred surf range."],
                "statusMessage": status_message,
                "station": payload["station"],
            }
        )
    except Exception as error:
        return jsonify({"error": str(error)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)
