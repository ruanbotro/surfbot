import express from "express";

const app = express();
const PORT = process.env.PORT || 3000;

const JACKSONVILLE = {
  name: "Jacksonville, FL",
  latitude: 30.3322,
  longitude: -81.6557
};

const SURF_THRESHOLDS = {
  minWaveHeightM: 0.8,
  maxWaveHeightM: 2.5,
  minWavePeriodS: 6,
  maxWindSpeedMps: 10
};

function buildMarineUrl() {
  const { latitude, longitude } = JACKSONVILLE;
  const params = new URLSearchParams({
    latitude: latitude.toString(),
    longitude: longitude.toString(),
    hourly: "wave_height,wave_period,wind_speed_10m",
    forecast_days: "1"
  });
  return `https://marine-api.open-meteo.com/v1/marine?${params.toString()}`;
}

function pickClosestHourIndex(times) {
  if (!Array.isArray(times) || times.length === 0) {
    return 0;
  }
  const now = Date.now();
  let closestIndex = 0;
  let closestDiff = Infinity;
  for (let i = 0; i < times.length; i += 1) {
    const diff = Math.abs(new Date(times[i]).getTime() - now);
    if (diff < closestDiff) {
      closestDiff = diff;
      closestIndex = i;
    }
  }
  return closestIndex;
}

function assessSurf({ waveHeight, wavePeriod, windSpeed }) {
  const meetsWaveHeight =
    waveHeight >= SURF_THRESHOLDS.minWaveHeightM &&
    waveHeight <= SURF_THRESHOLDS.maxWaveHeightM;
  const meetsWavePeriod = wavePeriod >= SURF_THRESHOLDS.minWavePeriodS;
  const meetsWind = windSpeed <= SURF_THRESHOLDS.maxWindSpeedMps;

  const goodSurf = meetsWaveHeight && meetsWavePeriod && meetsWind;

  const reasons = [];
  if (!meetsWaveHeight) {
    reasons.push(
      `Wave height (${waveHeight.toFixed(1)} m) should be between ${SURF_THRESHOLDS.minWaveHeightM} and ${SURF_THRESHOLDS.maxWaveHeightM} m.`
    );
  }
  if (!meetsWavePeriod) {
    reasons.push(
      `Wave period (${wavePeriod.toFixed(0)} s) should be at least ${SURF_THRESHOLDS.minWavePeriodS} s.`
    );
  }
  if (!meetsWind) {
    reasons.push(
      `Wind speed (${windSpeed.toFixed(1)} m/s) should be below ${SURF_THRESHOLDS.maxWindSpeedMps} m/s.`
    );
  }

  return { goodSurf, reasons };
}

app.get("/", (_req, res) => {
  res.type("html").send(`<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
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
  <main class="card">
    <header>
      <h1>Jacksonville Surf Conditions</h1>
      <p>Live marine forecast for Jacksonville, FL.</p>
    </header>
    <section id="status" class="status">Loading latest surf report...</section>
    <section class="metrics">
      <div class="metric">
        <span>Wave Height</span>
        <strong id="wave-height">--</strong>
      </div>
      <div class="metric">
        <span>Wave Period</span>
        <strong id="wave-period">--</strong>
      </div>
      <div class="metric">
        <span>Wind Speed</span>
        <strong id="wind-speed">--</strong>
      </div>
      <div class="metric">
        <span>Data Time</span>
        <strong id="data-time">--</strong>
      </div>
    </section>
    <section>
      <h2>Why this call?</h2>
      <ul id="reasons">
        <li>Loading thresholds...</li>
      </ul>
    </section>
    <div class="footer">Data source: Open-Meteo Marine API.</div>
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
        if (!response.ok) {
          throw new Error('Unable to load surf data');
        }
        const data = await response.json();

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
        statusEl.textContent = 'Unable to load surf report right now.';
        statusEl.classList.add('bad');
        reasonsEl.innerHTML = '<li>Please try again later.</li>';
      }
    }

    loadSurf();
  </script>
</body>
</html>`);
});

app.get("/api/surf", async (_req, res) => {
  try {
    const marineUrl = buildMarineUrl();
    const response = await fetch(marineUrl);
    if (!response.ok) {
      throw new Error("Marine API request failed");
    }
    const data = await response.json();
    const times = data?.hourly?.time ?? [];
    const waveHeights = data?.hourly?.wave_height ?? [];
    const wavePeriods = data?.hourly?.wave_period ?? [];
    const windSpeeds = data?.hourly?.wind_speed_10m ?? [];

    const index = pickClosestHourIndex(times);

    const waveHeight = waveHeights[index] ?? 0;
    const wavePeriod = wavePeriods[index] ?? 0;
    const windSpeed = windSpeeds[index] ?? 0;

    const { goodSurf, reasons } = assessSurf({
      waveHeight,
      wavePeriod,
      windSpeed
    });

    const statusMessage = goodSurf
      ? "Good surf right now — grab your board!"
      : "Surf conditions are not great right now.";

    res.json({
      location: JACKSONVILLE.name,
      time: times[index],
      waveHeight,
      wavePeriod,
      windSpeed,
      goodSurf,
      reasons: reasons.length
        ? reasons
        : ["All key thresholds are within the preferred surf range."],
      statusMessage
    });
  } catch (error) {
    res.status(500).json({
      error: "Unable to load surf data"
    });
  }
});

app.listen(PORT, () => {
  console.log(`Surf dashboard running on port ${PORT}`);
});
