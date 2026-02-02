from __future__ import annotations

import os
import json
import urllib.request
from datetime import datetime, timezone

from flask import Flask, jsonify, Response

app = Flask(__name__)

JACKSONVILLE = {
    "name": "Jacksonville, FL",
    "latitude": 30.398000,
    "longitude": -81.428000,
}

SURF_THRESHOLDS = {
    "min_wave_height_ft": 2.5,
    "max_wave_height_ft": 8.0,
    "min_wave_period_s": 6,
}


def build_marine_url(latitude: float, longitude: float) -> str:
    return (
        "https://marine-api.open-meteo.com/v1/marine"
        f"?latitude={latitude}"
        f"&longitude={longitude}"
        "&current=wave_height,wave_period,wave_direction,"
        "sea_surface_temperature,sea_level_height_msl"
        "&timezone=auto"
        "&cell_selection=sea"
        "&length_unit=imperial"
    )


def fetch_marine_forecast() -> dict:
    marine_url = build_marine_url(
        JACKSONVILLE["latitude"], JACKSONVILLE["longitude"]
    )
    request = urllib.request.Request(
        marine_url,
        headers={
            "User-Agent": "surfbot/1.0 (+https://open-meteo.com/)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        current = payload.get("current")
        if not current:
            raise ValueError("Missing current conditions in response.")

        return {
            "time": current["time"],
            "wave_height_ft": float(current["wave_height"]),
            "wave_period_s": float(current["wave_period"]),
            "wave_direction_deg": float(current["wave_direction"]),
            "sea_surface_temp": float(current["sea_surface_temperature"]),
            "sea_level_height_ft": float(current["sea_level_height_msl"]),
            "station": f"{JACKSONVILLE['name']} (Open-Meteo)",
            "source": "Open-Meteo Marine API",
            "is_fallback": False,
            "warnings": [],
        }
    except Exception as error:
        fallback_time = datetime.now(timezone.utc).isoformat()
        return {
            "time": fallback_time,
            "wave_height_ft": 3.5,
            "wave_period_s": 7.0,
            "wave_direction_deg": 95.0,
            "sea_surface_temp": 26.0,
            "sea_level_height_ft": 0.7,
            "station": "Backup estimate for Jacksonville, FL",
            "source": "Fallback estimate (local backup)",
            "is_fallback": True,
            "warnings": [
                "Live marine data is temporarily unavailable.",
                "Displaying a resilient backup estimate to keep the dashboard running.",
                str(error),
            ],
        }


def assess_surf(wave_height: float, wave_period: float) -> dict:
    meets_wave_height = (
        SURF_THRESHOLDS["min_wave_height_ft"]
        <= wave_height
        <= SURF_THRESHOLDS["max_wave_height_ft"]
    )
    meets_wave_period = wave_period >= SURF_THRESHOLDS["min_wave_period_s"]

    good_surf = meets_wave_height and meets_wave_period
    reasons: list[str] = []

    if not meets_wave_height:
        reasons.append(
            "Wave height ({:.1f} ft) should be between {} and {} ft.".format(
                wave_height,
                SURF_THRESHOLDS["min_wave_height_ft"],
                SURF_THRESHOLDS["max_wave_height_ft"],
            )
        )
    if not meets_wave_period:
        reasons.append(
            "Wave period ({:.0f} s) should be at least {} s.".format(
                wave_period, SURF_THRESHOLDS["min_wave_period_s"]
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
      color-scheme: light;
      font-family: "Poppins", "Trebuchet MS", system-ui, sans-serif;
      background: #082c3b;
      color: #fdf6e8;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at 15% 10%, rgba(255, 214, 149, 0.35), transparent 45%),
        radial-gradient(circle at 80% 15%, rgba(115, 197, 187, 0.35), transparent 45%),
        linear-gradient(160deg, #0a4b5f 0%, #0c6a77 40%, #1c8ea2 65%, #f1d3a5 100%);
      background-attachment: fixed;
    }
    .card {
      width: min(720px, 92vw);
      padding: 32px;
      border-radius: 20px;
      background:
        linear-gradient(145deg, rgba(11, 68, 80, 0.95), rgba(7, 41, 54, 0.95)),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'%3E%3Cpath fill='none' stroke='rgba(255,214,149,0.15)' stroke-width='2' d='M0 40h160M0 80h160M0 120h160'/%3E%3C/svg%3E");
      border: 2px solid rgba(255, 214, 149, 0.5);
      box-shadow:
        0 24px 50px rgba(5, 30, 38, 0.45),
        inset 0 0 0 1px rgba(255, 214, 149, 0.2);
      display: grid;
      gap: 20px;
    }
    h1 {
      margin: 0;
      font-size: 2.2rem;
      letter-spacing: 0.02em;
    }
    .tagline {
      margin: 6px 0 0;
      font-size: 0.95rem;
      color: rgba(253, 246, 232, 0.8);
      text-transform: uppercase;
      letter-spacing: 0.18em;
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
      background: rgba(255, 214, 149, 0.22);
      border: 1px solid rgba(255, 214, 149, 0.6);
      color: #fff1d6;
    }
    .status.bad {
      background: rgba(255, 141, 112, 0.25);
      border: 1px solid rgba(255, 141, 112, 0.5);
      color: #ffe0d5;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 16px;
    }
    .metric {
      padding: 14px 16px;
      background: rgba(10, 52, 64, 0.75);
      border: 1px solid rgba(255, 214, 149, 0.25);
      border-radius: 14px;
    }
    .metric span {
      display: block;
      font-size: 0.85rem;
      opacity: 0.75;
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
      <p class="tagline">Aloha swell report</p>
      <p>Latest marine snapshot near Jacksonville, FL.</p>
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
        <span>Wave Direction</span>
        <strong id=\"wave-direction\">--</strong>
      </div>
      <div class=\"metric\">
        <span>Sea Surface Temp</span>
        <strong id=\"sea-surface-temp\">--</strong>
      </div>
      <div class=\"metric\">
        <span>Sea Level Height</span>
        <strong id=\"sea-level-height\">--</strong>
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
    <div class=\"footer\" id=\"data-source\">Data source: --</div>
  </main>

  <script>
    async function loadSurf() {
      const statusEl = document.getElementById('status');
      const waveHeightEl = document.getElementById('wave-height');
      const wavePeriodEl = document.getElementById('wave-period');
      const waveDirectionEl = document.getElementById('wave-direction');
      const seaSurfaceTempEl = document.getElementById('sea-surface-temp');
      const seaLevelHeightEl = document.getElementById('sea-level-height');
      const dataTimeEl = document.getElementById('data-time');
      const reasonsEl = document.getElementById('reasons');
      const sourceEl = document.getElementById('data-source');
      const fallbackPayload = {
        time: new Date().toISOString(),
        waveHeight: 3.5,
        wavePeriod: 7.0,
        waveDirection: 95.0,
        seaSurfaceTemp: 26.0,
        seaLevelHeight: 0.7,
        goodSurf: true,
        reasons: [
          'Live marine data is temporarily unavailable.',
          'Showing the most reliable backup estimate.',
        ],
        statusMessage: 'Backup data loaded — surf estimate only.',
        source: 'Fallback estimate (local backup)',
        isFallback: true,
      };

      try {
        const response = await fetch('/api/surf');
        const data = await response.json();
        if (!response.ok) {
          throw new Error('Unable to load live data.');
        }

        statusEl.textContent = data.statusMessage;
        statusEl.classList.remove('good', 'bad');
        statusEl.classList.add(data.goodSurf ? 'good' : 'bad');

        waveHeightEl.textContent = `${data.waveHeight.toFixed(1)} ft`;
        wavePeriodEl.textContent = `${data.wavePeriod.toFixed(0)} s`;
        waveDirectionEl.textContent = `${data.waveDirection.toFixed(0)}°`;
        seaSurfaceTempEl.textContent = `${data.seaSurfaceTemp.toFixed(1)}°C`;
        seaLevelHeightEl.textContent = `${data.seaLevelHeight.toFixed(1)} ft`;
        dataTimeEl.textContent = new Date(data.time).toLocaleString();

        reasonsEl.innerHTML = '';
        data.reasons.forEach((reason) => {
          const li = document.createElement('li');
          li.textContent = reason;
          reasonsEl.appendChild(li);
        });
        sourceEl.textContent = `Data source: ${data.source || 'Open-Meteo Marine API'}`;
      } catch (error) {
        statusEl.textContent = fallbackPayload.statusMessage;
        statusEl.classList.remove('bad');
        statusEl.classList.add('good');
        waveHeightEl.textContent = `${fallbackPayload.waveHeight.toFixed(1)} ft`;
        wavePeriodEl.textContent = `${fallbackPayload.wavePeriod.toFixed(0)} s`;
        waveDirectionEl.textContent = `${fallbackPayload.waveDirection.toFixed(0)}°`;
        seaSurfaceTempEl.textContent = `${fallbackPayload.seaSurfaceTemp.toFixed(1)}°C`;
        seaLevelHeightEl.textContent = `${fallbackPayload.seaLevelHeight.toFixed(1)} ft`;
        dataTimeEl.textContent = new Date(
          fallbackPayload.time
        ).toLocaleString();
        reasonsEl.innerHTML = '';
        fallbackPayload.reasons.forEach((reason) => {
          const li = document.createElement('li');
          li.textContent = reason;
          reasonsEl.appendChild(li);
        });
        sourceEl.textContent = `Data source: ${fallbackPayload.source}`;
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

        wave_height = payload["wave_height_ft"]
        wave_period = payload["wave_period_s"]
        wave_direction = payload["wave_direction_deg"]
        sea_surface_temp = payload["sea_surface_temp"]
        sea_level_height = payload["sea_level_height_ft"]

        assessment = assess_surf(wave_height, wave_period)

        if payload.get("is_fallback"):
            status_message = "Backup data loaded — surf estimate only."
        else:
            status_message = (
                "Good surf right now — grab your board!"
                if assessment["good_surf"]
                else "Surf conditions are not great right now."
            )

        reasons = assessment["reasons"] or [
            "All key thresholds are within the preferred surf range."
        ]
        if payload.get("is_fallback"):
            reasons = payload.get("warnings", []) + reasons

        return jsonify(
            {
                "location": JACKSONVILLE["name"],
                "time": payload["time"],
                "waveHeight": wave_height,
                "wavePeriod": wave_period,
                "waveDirection": wave_direction,
                "seaSurfaceTemp": sea_surface_temp,
                "seaLevelHeight": sea_level_height,
                "goodSurf": assessment["good_surf"],
                "reasons": reasons,
                "statusMessage": status_message,
                "station": payload["station"],
                "source": payload.get("source", "Open-Meteo Marine API"),
                "isFallback": payload.get("is_fallback", False),
                "warnings": payload.get("warnings", []),
            }
        )
    except Exception as error:
        fallback_time = datetime.now(timezone.utc).isoformat()
        return jsonify(
            {
                "location": JACKSONVILLE["name"],
                "time": fallback_time,
                "waveHeight": 3.5,
                "wavePeriod": 7.0,
                "waveDirection": 95.0,
                "seaSurfaceTemp": 26.0,
                "seaLevelHeight": 0.7,
                "goodSurf": True,
                "reasons": [
                    "Live marine data is temporarily unavailable.",
                    "Displaying a resilient backup estimate.",
                ],
                "statusMessage": "Backup data loaded — surf estimate only.",
                "station": "Backup estimate for Jacksonville, FL",
                "source": "Fallback estimate (local backup)",
                "isFallback": True,
                "warnings": [str(error)],
            }
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)
