const express = require('express');
const { SSMClient, GetParameterCommand } = require('@aws-sdk/client-ssm');

const app = express();

const PORT = process.env.PORT || 3000;
const WEATHER_URL = process.env.WEATHER_URL;

const GEMINI_API_BASE =
  process.env.GEMINI_API_BASE ||
  'https://generativelanguage.googleapis.com';

const GEMINI_MODEL =
  process.env.GEMINI_MODEL ||
  'gemini-3.1-flash-lite';

const KEY_PARAM =
  process.env.GEMINI_KEY_PARAM ||
  '/itmo-444-544/gemini-api-key';

const KEY_CACHE_MS =
  Number(process.env.KEY_CACHE_SECONDS || 300) * 1000;

const ssm = new SSMClient({
  region: process.env.AWS_REGION,
});

let cachedKey = {
  value: null,
  at: 0,
};

const log = (event, fields = {}) =>
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      event,
      ...fields,
    })
  );


async function getApiKey() {
  if (process.env.GEMINI_API_KEY) {
    return process.env.GEMINI_API_KEY;
  }

  if (
    cachedKey.value &&
    Date.now() - cachedKey.at < KEY_CACHE_MS
  ) {
    return cachedKey.value;
  }

  const out = await ssm.send(
    new GetParameterCommand({
      Name: KEY_PARAM,
      WithDecryption: true,
    })
  );

  cachedKey = {
    value: out.Parameter.Value,
    at: Date.now(),
  };

  return cachedKey.value;
}


const SYSTEM_PROMPT =
  'You give a short clothing suggestion for the weather you are given. ' +
  'Reply in at most two plain sentences, with no markdown and no lists. ' +
  'Use only the data provided.';


function buildPrompt(w) {
  const f = w.forecast;

  return [
    `Zip code: ${w.zip} (${w.city}, ${w.state})`,
    `Period: ${f.name}`,
    `Temperature: ${f.temperature} ${f.temperatureUnit}`,
    `Conditions: ${f.shortForecast}`,
    `Wind: ${f.windSpeed}`,
    `Chance of precipitation: ${
      f.precipitationChance === null
        ? 'unknown'
        : f.precipitationChance + ' percent'
    }`,
  ].join('\n');
}


async function askGemini(prompt) {
  const key = await getApiKey();

  const res = await fetch(
    `${GEMINI_API_BASE}/v1beta/models/${GEMINI_MODEL}:generateContent`,
    {
      method: 'POST',

      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': key,
      },

      body: JSON.stringify({
        systemInstruction: {
          parts: [
            {
              text: SYSTEM_PROMPT,
            },
          ],
        },

        contents: [
          {
            parts: [
              {
                text: prompt,
              },
            ],
          },
        ],

        generationConfig: {
          maxOutputTokens: 300,
        },
      }),

      signal: AbortSignal.timeout(15000),
    }
  );

  if (!res.ok) {
    const err = new Error(
      'gemini_http_error'
    );

    err.status = res.status;
    throw err;
  }

  const data = await res.json();

  const parts =
    (
      data.candidates &&
      data.candidates[0] &&
      data.candidates[0].content.parts
    ) || [];

  const text = parts
    .map((p) => p.text || '')
    .join('')
    .trim();

  if (!text) {
    const err = new Error(
      'gemini_empty_response'
    );

    err.status = 200;
    throw err;
  }

  return text;
}


function fallbackAdvice(f) {
  const t = f.temperature;

  let base;

  if (t <= 32) {
    base =
      'Wear a heavy coat, a hat and gloves.';
  } else if (t <= 50) {
    base =
      'Wear a warm jacket and long pants.';
  } else if (t <= 68) {
    base =
      'Wear a light jacket or a sweater over long sleeves.';
  } else if (t <= 80) {
    base =
      'A t-shirt and light pants or shorts will be fine.';
  } else {
    base =
      'Wear light, breathable clothes and bring water and sunscreen.';
  }

  const wet =
    (f.precipitationChance || 0) >= 40 ||
    /rain|shower|storm|snow/i.test(
      f.shortForecast
    );

  return wet
    ? `${base} Bring an umbrella or a waterproof jacket.`
    : base;
}


const escapeHtml = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[c]
  );


async function getAdvice(zip) {
  if (!/^\d{5}$/.test(zip)) {
    log(
      'advice_rejected',
      {
        reason: 'invalid_zip',
      }
    );

    return {
      status: 400,
      body: {
        error: 'invalid_zip',
        message:
          'Give a 5 digit US zip code.',
      },
    };
  }

  const started = Date.now();

  log(
    'advice_request',
    { zip }
  );

  let weather;

  try {
    const res = await fetch(
      `${WEATHER_URL}/weather?zip=${zip}`,
      {
        signal:
          AbortSignal.timeout(
            20000
          ),
      }
    );

    if (
      res.status === 400 ||
      res.status === 404
    ) {
      log(
        'advice_rejected',
        {
          reason:
            'weather_' +
            res.status,
          zip,
        }
      );

      return {
        status: res.status,
        body: await res.json(),
      };
    }

    if (!res.ok) {
      throw new Error(
        'weather_status_' +
          res.status
      );
    }

    weather = await res.json();
  } catch (err) {
    log(
      'weather_call_failed',
      {
        zip,
        message: err.message,
      }
    );

    return {
      status: 502,
      body: {
        error:
          'weather_service_unavailable',
      },
    };
  }

  let advice;
  let source;

  try {
    advice = await askGemini(
      buildPrompt(weather)
    );

    source = 'gemini';
  } catch (err) {
    log(
      'gemini_error',
      {
        zip,
        status:
          err.status || 0,
        reason:
          err.name ===
          'TimeoutError'
            ? 'timeout'
            : err.message,
      }
    );

    advice = fallbackAdvice(
      weather.forecast
    );

    source = 'fallback';
  }

  log(
    'advice_success',
    {
      zip,
      source,
      ms:
        Date.now() -
        started,
    }
  );

  return {
    status: 200,

    body: {
      ...weather,
      advice,
      source,
      model:
        source === 'gemini'
          ? GEMINI_MODEL
          : null,
    },
  };
}


app.get(
  '/advice',
  async (req, res) => {
    const { status, body } =
      await getAdvice(
        String(
          req.query.zip || ''
        )
      );

    res
      .status(status)
      .json(body);
  }
);


app.get(
  '/',
  async (req, res) => {
    const form = `
      <form method="GET" action="/">
        <label>
          US zip code
          <input
            name="zip"
            pattern="[0-9]{5}"
            maxlength="5"
            required
          >
        </label>
        <button type="submit">
          What should I wear?
        </button>
      </form>
    `;

    let result = '';

    if (req.query.zip) {
      const {
        status,
        body,
      } = await getAdvice(
        String(req.query.zip)
      );

      if (status === 200) {
        const f =
          body.forecast;

        result = `
          <h2>
            ${escapeHtml(body.city)},
            ${escapeHtml(body.state)}
            ${escapeHtml(body.zip)}
          </h2>

          <p>
            ${escapeHtml(f.name)}:
            ${escapeHtml(f.temperature)}
            ${escapeHtml(f.temperatureUnit)},
            ${escapeHtml(f.shortForecast)},
            wind ${escapeHtml(f.windSpeed)}
          </p>

          <p>
            <strong>
              ${escapeHtml(body.advice)}
            </strong>
          </p>

          <p>
            <small>
              Suggestion source:
              ${escapeHtml(body.source)}
            </small>
          </p>
        `;
      } else {
        result = `
          <p>
            Sorry:
            ${escapeHtml(body.error)}
          </p>
        `;
      }
    }

    res.send(`
      <h1>Weather Advisor</h1>
      ${form}
      ${result}
    `);
  }
);


app.listen(
  PORT,
  () => {
    log(
      'advisor_started',
      {
        port: PORT,
        model: GEMINI_MODEL,
      }
    );
  }
);
