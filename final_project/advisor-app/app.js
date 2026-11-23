const crypto = require('crypto');
const express = require('express');

const {
  SSMClient,
  GetParameterCommand,
} = require('@aws-sdk/client-ssm');

const {
  DynamoDBClient,
} = require('@aws-sdk/client-dynamodb');

const {
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  UpdateCommand,
} = require('@aws-sdk/lib-dynamodb');

const {
  SNSClient,
  SubscribeCommand,
  PublishCommand,
} = require('@aws-sdk/client-sns');


const app = express();

app.use(
  express.urlencoded({
    extended: false,
    limit: '8kb',
  })
);


const PORT =
  Number(
    process.env.PORT || 3000
  );

const WEATHER_URL =
  process.env.WEATHER_URL;

const GEMINI_API_BASE =
  process.env.GEMINI_API_BASE ||
  'https://generativelanguage.googleapis.com';

const GEMINI_MODEL =
  process.env.GEMINI_MODEL ||
  'gemini-3.1-flash-lite';

const GEMINI_KEY_PARAM =
  process.env.GEMINI_KEY_PARAM ||
  '/itmo-444-544/gemini-api-key';

const KEY_CACHE_SECONDS =
  Number(
    process.env.KEY_CACHE_SECONDS ||
    300
  );

const ADVISOR_TABLE =
  process.env.ADVISOR_TABLE ||
  'weather-advisor-reports';

const REPORT_TTL_SECONDS =
  Number(
    process.env.REPORT_TTL_SECONDS ||
    1800
  );

const DAILY_GEMINI_CAP =
  Number(
    process.env.DAILY_GEMINI_CAP ||
    100
  );

const SNS_TOPIC_ARN =
  process.env.SNS_TOPIC_ARN ||
  '';

const EMAIL_LIMIT =
  Number(
    process.env.EMAIL_LIMIT ||
    5
  );


const ssm =
  new SSMClient({
    region:
      process.env.AWS_REGION,
  });

const sns =
  new SNSClient({
    region:
      process.env.AWS_REGION,
  });

const ddb =
  DynamoDBDocumentClient.from(
    new DynamoDBClient({
      region:
        process.env.AWS_REGION,
    })
  );


let cachedKey = {
  value: null,
  at: 0,
};


const visitorRequests =
  new Map();

const visitorEmails =
  new Map();


const GENDERS = {
  women: 'womenswear',
  men: 'menswear',
  neutral: 'neutral',
};


function log(
  event,
  fields
) {
  console.log(
    JSON.stringify({
      ts:
        new Date()
          .toISOString(),
      event:
        event,
      ...(fields || {}),
    })
  );
}


function escapeHtml(value) {
  return String(
    value === null ||
    value === undefined
      ? ''
      : value
  ).replace(
    /[&<>"']/g,
    function (character) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }[character];
    }
  );
}


function normalizeEmail(
  value
) {
  return String(
    value || ''
  )
    .trim()
    .toLowerCase();
}


function validEmail(
  value
) {
  if (
    !value ||
    value.length > 254
  ) {
    return false;
  }

  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    .test(value);
}


function realDate(
  value
) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/
      .test(value)
  ) {
    return false;
  }

  const date =
    new Date(
      value +
      'T00:00:00Z'
    );

  return (
    !Number.isNaN(
      date.getTime()
    ) &&
    date
      .toISOString()
      .slice(0, 10) ===
      value
  );
}


function visitorId(
  req
) {
  const input =
    req.ip ||
    (
      req.socket &&
      req.socket.remoteAddress
    ) ||
    'unknown';

  return crypto
    .createHash('sha256')
    .update(String(input))
    .digest('hex')
    .slice(0, 24);
}


function localRateLimit(
  store,
  key,
  limit,
  windowMs
) {
  const now =
    Date.now();

  const current =
    store.get(key);

  if (
    !current ||
    now >= current.reset
  ) {
    store.set(
      key,
      {
        count: 1,
        reset:
          now + windowMs,
      }
    );

    return true;
  }

  if (
    current.count >= limit
  ) {
    return false;
  }

  current.count += 1;
  return true;
}


function reportKey(
  zip,
  date,
  gender
) {
  const hash =
    crypto
      .createHash('sha256')
      .update(
        zip +
        '|' +
        date +
        '|' +
        gender
      )
      .digest('hex');

  return (
    'report#' +
    hash
  );
}


async function getApiKey() {
  if (
    cachedKey.value &&
    Date.now() -
      cachedKey.at <
      KEY_CACHE_SECONDS *
      1000
  ) {
    return cachedKey.value;
  }

  const result =
    await ssm.send(
      new GetParameterCommand({
        Name:
          GEMINI_KEY_PARAM,

        WithDecryption:
          true,
      })
    );

  cachedKey = {
    value:
      result.Parameter.Value,

    at:
      Date.now(),
  };

  return cachedKey.value;
}


async function getSavedReport(
  key
) {
  try {
    const result =
      await ddb.send(
        new GetCommand({
          TableName:
            ADVISOR_TABLE,

          Key: {
            item_key:
              key,
          },
        })
      );

    const item =
      result.Item;

    if (!item) {
      return null;
    }

    const now =
      Math.floor(
        Date.now() / 1000
      );

    if (
      item.expires_at <=
      now
    ) {
      return null;
    }

    return item.report;
  } catch (err) {
    log(
      'report_cache_read_error',
      {
        message:
          err.message,
      }
    );

    return null;
  }
}


async function saveReport(
  key,
  report
) {
  try {
    const now =
      Math.floor(
        Date.now() / 1000
      );

    await ddb.send(
      new PutCommand({
        TableName:
          ADVISOR_TABLE,

        Item: {
          item_key:
            key,

          report:
            report,

          created_at:
            now,

          expires_at:
            now +
            REPORT_TTL_SECONDS,
        },
      })
    );
  } catch (err) {
    log(
      'report_cache_write_error',
      {
        message:
          err.message,
      }
    );
  }
}


function utcDay() {
  return new Date()
    .toISOString()
    .slice(0, 10);
}


async function reserveGeminiCall() {
  const today =
    utcDay();

  const key =
    'gemini-counter#' +
    today;

  const tomorrow =
    Math.floor(
      Date.now() /
      1000
    ) +
    2 * 86400;

  try {
    const result =
      await ddb.send(
        new UpdateCommand({
          TableName:
            ADVISOR_TABLE,

          Key: {
            item_key:
              key,
          },

          UpdateExpression:
            'SET #count = if_not_exists(#count, :zero) + :one, expires_at = :ttl',

          ConditionExpression:
            'attribute_not_exists(#count) OR #count < :cap',

          ExpressionAttributeNames: {
            '#count':
              'count',
          },

          ExpressionAttributeValues: {
            ':zero':
              0,

            ':one':
              1,

            ':cap':
              DAILY_GEMINI_CAP,

            ':ttl':
              tomorrow,
          },

          ReturnValues:
            'ALL_NEW',
        })
      );

    return {
      allowed: true,

      count:
        result.Attributes.count,
    };
  } catch (err) {
    if (
      err.name ===
      'ConditionalCheckFailedException'
    ) {
      return {
        allowed:
          false,
      };
    }

    /*
    If DynamoDB is unavailable,
    do not call a limited external
    model without a working cap.
    */
    log(
      'gemini_counter_error',
      {
        message:
          err.message,
      }
    );

    return {
      allowed:
        false,
    };
  }
}


function geminiFacts(
  weather
) {
  return {
    date:
      weather.date,

    timezone:
      weather.timezone,

    morning:
      weather.periods.morning,

    night:
      weather.periods.night,
  };
}


const SYSTEM_PROMPT = [
  'You are the advice component of a weather application.',
  'Return JSON only.',
  'Do not invent, repeat, alter, estimate, or calculate weather measurements.',
  'Use only the supplied weather facts.',
  'If a fact is unavailable, do not rely on it.',
  'Return exactly morning and night.',
  'Each period must contain road, dressing, and accessories.',
  'Each value must be a short practical plain-text sentence under 180 characters.',
  'Do not include markdown.',
].join(' ');


function buildPrompt(
  weather,
  clothingCategory
) {
  return JSON.stringify({
    clothing_category:
      clothingCategory,

    weather_facts:
      geminiFacts(
        weather
      ),

    required_shape: {
      morning: {
        road:
          'short string',

        dressing:
          'short string',

        accessories:
          'short string',
      },

      night: {
        road:
          'short string',

        dressing:
          'short string',

        accessories:
          'short string',
      },
    },
  });
}


function validAdviceText(
  value
) {
  return (
    typeof value ===
      'string' &&
    value.trim().length >
      0 &&
    value.length <= 180
  );
}


function validateAdvice(
  value
) {
  if (
    !value ||
    typeof value !==
      'object'
  ) {
    return false;
  }

  const periods = [
    'morning',
    'night',
  ];

  const fields = [
    'road',
    'dressing',
    'accessories',
  ];

  for (
    const period of periods
  ) {
    if (
      !value[period] ||
      typeof value[period] !==
        'object'
    ) {
      return false;
    }

    for (
      const field of fields
    ) {
      if (
        !validAdviceText(
          value[period][field]
        )
      ) {
        return false;
      }
    }
  }

  return true;
}


async function askGemini(
  weather,
  clothingCategory
) {
  const reservation =
    await reserveGeminiCall();

  if (
    !reservation.allowed
  ) {
    const error =
      new Error(
        'gemini_daily_cap'
      );

    error.reason =
      'daily_cap';

    throw error;
  }

  const key =
    await getApiKey();

  const response =
    await fetch(
      GEMINI_API_BASE +
      '/v1beta/models/' +
      encodeURIComponent(
        GEMINI_MODEL
      ) +
      ':generateContent',
      {
        method: 'POST',

        headers: {
          'Content-Type':
            'application/json',

          'x-goog-api-key':
            key,
        },

        body:
          JSON.stringify({
            systemInstruction: {
              parts: [
                {
                  text:
                    SYSTEM_PROMPT,
                },
              ],
            },

            contents: [
              {
                parts: [
                  {
                    text:
                      buildPrompt(
                        weather,
                        clothingCategory
                      ),
                  },
                ],
              },
            ],

            generationConfig: {
              responseMimeType:
                'application/json',

              maxOutputTokens:
                700,

              temperature:
                0.2,
            },
          }),

        signal:
          AbortSignal.timeout(
            15000
          ),
      }
    );

  if (
    !response.ok
  ) {
    const error =
      new Error(
        'gemini_http_error'
      );

    error.status =
      response.status;

    throw error;
  }

  const data =
    await response.json();

  const candidates =
    data.candidates ||
    [];

  if (
    !candidates.length ||
    !candidates[0].content
  ) {
    throw new Error(
      'gemini_empty_response'
    );
  }

  const parts =
    candidates[0]
      .content.parts ||
    [];

  const text =
    parts
      .map(function (
        part
      ) {
        return (
          part.text || ''
        );
      })
      .join('')
      .trim();

  let parsed;

  try {
    parsed =
      JSON.parse(text);
  } catch (err) {
    throw new Error(
      'gemini_invalid_json'
    );
  }

  if (
    !validateAdvice(
      parsed
    )
  ) {
    throw new Error(
      'gemini_invalid_shape'
    );
  }

  return parsed;
}


function fallbackForPeriod(
  facts,
  clothingCategory
) {
  const temperature =
    facts.temperature &&
    facts.temperature
      .average_f !== null
      ? Number(
          facts.temperature
            .average_f
        )
      : null;

  const wind =
    facts.wind_speed &&
    facts.wind_speed
      .max_mph !== null
      ? Number(
          facts.wind_speed
            .max_mph
        )
      : null;

  const visibility =
    facts.visibility &&
    facts.visibility
      .min_miles !== null
      ? Number(
          facts.visibility
            .min_miles
        )
      : null;

  const uv =
    facts.uv &&
    facts.uv.max_index !==
      null
      ? Number(
          facts.uv
            .max_index
        )
      : null;

  const rain =
    facts.rain
      ? facts.rain.category
      : 'No';

  const snow =
    facts.snow
      ? facts.snow.category
      : 'No';


  let road =
    'Normal driving conditions are expected, but continue to watch local conditions.';

  if (
    snow !== 'No'
  ) {
    road =
      snow === 'Heavy'
        ? 'Expect hazardous snowy or icy roads; avoid unnecessary travel and allow extra stopping distance.'
        : 'Snow may make roads slick; reduce speed and allow extra stopping distance.';
  } else if (
    rain !== 'No'
  ) {
    road =
      rain === 'Heavy'
        ? 'Heavy rain may cause slick roads and poor visibility; slow down and allow extra stopping distance.'
        : 'Wet roads are possible; reduce speed and allow additional stopping distance.';
  } else if (
    visibility !== null &&
    visibility < 3
  ) {
    road =
      'Visibility may be poor; use headlights, slow down, and increase following distance.';
  } else if (
    wind !== null &&
    wind >= 30
  ) {
    road =
      'Strong winds may affect high-profile vehicles; keep both hands on the wheel and reduce speed.';
  }


  let dressing =
    'Choose comfortable clothing suitable for the conditions.';

  if (
    temperature !== null
  ) {
    if (
      temperature <= 32
    ) {
      dressing =
        'Wear an insulated coat with warm layers, long pants, gloves, and a hat.';
    } else if (
      temperature <= 50
    ) {
      dressing =
        'Wear a warm jacket or coat with long pants and closed shoes.';
    } else if (
      temperature <= 68
    ) {
      dressing =
        'Wear light layers such as a sweater or light jacket with long pants.';
    } else if (
      temperature <= 80
    ) {
      dressing =
        'Wear light comfortable clothing such as a shirt with lightweight pants or shorts.';
    } else {
      dressing =
        'Wear lightweight breathable clothing and stay hydrated.';
    }
  }

  if (
    clothingCategory ===
    'womenswear'
  ) {
    dressing +=
      ' Choose the equivalent comfortable womenswear style you prefer.';
  } else if (
    clothingCategory ===
    'menswear'
  ) {
    dressing +=
      ' Choose the equivalent comfortable menswear style you prefer.';
  }


  const accessories = [];

  if (
    rain !== 'No'
  ) {
    accessories.push(
      'an umbrella or waterproof layer'
    );
  }

  if (
    snow !== 'No' ||
    (
      temperature !== null &&
      temperature <= 40
    )
  ) {
    accessories.push(
      'gloves and a warm hat'
    );
  }

  if (
    uv !== null &&
    uv >= 3
  ) {
    accessories.push(
      'sunscreen and sunglasses'
    );
  }

  if (
    wind !== null &&
    wind >= 20
  ) {
    accessories.push(
      'a secure outer layer'
    );
  }

  return {
    road:
      road,

    dressing:
      dressing,

    accessories:
      accessories.length
        ? 'Carry ' +
          accessories.join(
            ', '
          ) +
          '.'
        : 'No special weather accessory is required, but carry your usual essentials.',
  };
}


function fallbackAdvice(
  weather,
  clothingCategory
) {
  return {
    morning:
      fallbackForPeriod(
        weather.periods
          .morning,
        clothingCategory
      ),

    night:
      fallbackForPeriod(
        weather.periods
          .night,
        clothingCategory
      ),
  };
}


async function fetchWeather(
  zip,
  date
) {
  const response =
    await fetch(
      WEATHER_URL +
      '/weather?zip=' +
      encodeURIComponent(
        zip
      ) +
      '&date=' +
      encodeURIComponent(
        date
      ),
      {
        signal:
          AbortSignal.timeout(
            15000
          ),
      }
    );

  let body = {};

  try {
    body =
      await response.json();
  } catch (err) {
    body = {};
  }

  return {
    status:
      response.status,

    body:
      body,
  };
}


async function buildReport(
  zip,
  date,
  gender
) {
  const key =
    reportKey(
      zip,
      date,
      gender
    );

  const saved =
    await getSavedReport(
      key
    );

  if (saved) {
    return {
      status: 200,

      report:
        saved,

      cache:
        'hit',

      key:
        key,
    };
  }

  const weatherResult =
    await fetchWeather(
      zip,
      date
    );

  if (
    weatherResult.status !==
    200
  ) {
    return {
      status:
        weatherResult.status,

      error:
        weatherResult.body,
    };
  }

  const weather =
    weatherResult.body;

  let advice;
  let source;

  try {
    advice =
      await askGemini(
        weather,
        GENDERS[gender]
      );

    source =
      'gemini';
  } catch (err) {
    log(
      'gemini_error',
      {
        reason:
          err.reason ||
          err.message,

        status:
          err.status || 0,
      }
    );

    advice =
      fallbackAdvice(
        weather,
        GENDERS[gender]
      );

    source =
      'rule-based fallback';
  }

  const report = {
    zip:
      zip,

    date:
      date,

    gender:
      gender,

    weather:
      weather,

    advice:
      advice,

    advice_source:
      source,

    created_at:
      new Date()
        .toISOString(),
  };

  await saveReport(
    key,
    report
  );

  return {
    status: 200,

    report:
      report,

    cache:
      'miss',

    key:
      key,
  };
}


function formatValue(
  value,
  suffix
) {
  if (
    value === null ||
    value === undefined ||
    value === ''
  ) {
    return (
      'Not available'
    );
  }

  return (
    escapeHtml(value) +
    (suffix || '')
  );
}


function periodCell(
  facts,
  advice,
  item
) {
  if (
    item ===
    'temperature'
  ) {
    return (
      formatValue(
        facts.temperature
          .low_f,
        '°F'
      ) +
      ' to ' +
      formatValue(
        facts.temperature
          .high_f,
        '°F'
      ) +
      '<br><small>' +
      escapeHtml(
        facts.temperature
          .source
      ) +
      '</small>'
    );
  }

  if (
    item ===
    'wind'
  ) {
    return (
      formatValue(
        facts.wind_speed
          .max_mph,
        ' mph'
      ) +
      '<br><small>' +
      escapeHtml(
        facts.wind_speed
          .source
      ) +
      '</small>'
    );
  }

  if (
    item ===
    'visibility'
  ) {
    return (
      formatValue(
        facts.visibility
          .min_miles,
        ' mi'
      ) +
      '<br><small>' +
      escapeHtml(
        facts.visibility
          .source
      ) +
      '</small>'
    );
  }

  if (
    item === 'uv'
  ) {
    return (
      formatValue(
        facts.uv
          .max_index,
        ''
      ) +
      '<br><small>' +
      escapeHtml(
        facts.uv.source
      ) +
      '</small>'
    );
  }

  if (
    item ===
    'humidity'
  ) {
    return (
      formatValue(
        facts.humidity
          .average_percent,
        '%'
      ) +
      '<br><small>' +
      escapeHtml(
        facts.humidity
          .source
      ) +
      '</small>'
    );
  }

  if (
    item === 'rain'
  ) {
    return (
      '<strong>' +
      escapeHtml(
        facts.rain.category
      ) +
      '</strong>' +
      '<br><small>' +
      escapeHtml(
        facts.rain.source
      ) +
      '</small>'
    );
  }

  if (
    item === 'snow'
  ) {
    return (
      '<strong>' +
      escapeHtml(
        facts.snow.category
      ) +
      '</strong>' +
      '<br><small>' +
      escapeHtml(
        facts.snow.source
      ) +
      '</small>'
    );
  }

  if (
    item === 'road'
  ) {
    return escapeHtml(
      advice.road
    );
  }

  if (
    item ===
    'dressing'
  ) {
    return escapeHtml(
      advice.dressing
    );
  }

  return escapeHtml(
    advice.accessories
  );
}


function reportTable(
  report
) {
  const morning =
    report.weather
      .periods.morning;

  const night =
    report.weather
      .periods.night;

  const morningAdvice =
    report.advice
      .morning;

  const nightAdvice =
    report.advice
      .night;

  const rows = [
    [
      'Temperature',
      'temperature',
    ],
    [
      'Wind speed',
      'wind',
    ],
    [
      'Visibility',
      'visibility',
    ],
    [
      'UV',
      'uv',
    ],
    [
      'Humidity',
      'humidity',
    ],
    [
      'Rain',
      'rain',
    ],
    [
      'Snow',
      'snow',
    ],
    [
      'Suggested road conditions',
      'road',
    ],
    [
      'Suggested dressing',
      'dressing',
    ],
    [
      'Suggested accessories',
      'accessories',
    ],
  ];

  return (
    '<table>' +
    '<thead>' +
    '<tr>' +
    '<th>Item</th>' +
    '<th>Morning<br><small>06:00-11:59 local</small></th>' +
    '<th>Night<br><small>18:00-23:59 local</small></th>' +
    '</tr>' +
    '</thead>' +
    '<tbody>' +
    rows
      .map(
        function (row) {
          return (
            '<tr>' +
            '<th>' +
            escapeHtml(
              row[0]
            ) +
            '</th>' +
            '<td>' +
            periodCell(
              morning,
              morningAdvice,
              row[1]
            ) +
            '</td>' +
            '<td>' +
            periodCell(
              night,
              nightAdvice,
              row[1]
            ) +
            '</td>' +
            '</tr>'
          );
        }
      )
      .join('') +
    '</tbody>' +
    '</table>'
  );
}


function page(
  title,
  body
) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
body {
  font-family: Arial, sans-serif;
  max-width: 1100px;
  margin: 30px auto;
  padding: 0 18px;
  line-height: 1.45;
  color: #202124;
}
h1, h2 { margin-bottom: 8px; }
form {
  display: grid;
  gap: 14px;
  max-width: 600px;
}
label {
  display: grid;
  gap: 5px;
  font-weight: 600;
}
input, select, button {
  font: inherit;
  padding: 9px;
}
button {
  cursor: pointer;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 20px 0;
}
th, td {
  border: 1px solid #bbb;
  padding: 10px;
  text-align: left;
  vertical-align: top;
}
thead th {
  background: #f2f2f2;
}
small {
  color: #555;
}
.notice {
  padding: 12px;
  background: #f5f5f5;
  margin: 14px 0;
}
.error {
  padding: 12px;
  border: 1px solid #aa0000;
}
</style>
</head>
<body>
${body}
</body>
</html>`;
}


function homePage(
  error
) {
  const errorHtml =
    error
      ? '<p class="error">' +
        escapeHtml(error) +
        '</p>'
      : '';

  return page(
    'Weather Advisor',
    `
<h1>Weather Advisor</h1>

<p>
Enter a US ZIP code and a date within the next seven days.
Gender is used only to tailor the clothing category.
Weather facts and a clothing category may be sent to Google Gemini.
Your email address is never sent to Gemini and is not stored with the report.
</p>

${errorHtml}

<form method="POST" action="/report">

<label>
Date
<input
  type="date"
  name="date"
  required
>
</label>

<label>
US ZIP code
<input
  name="zip"
  inputmode="numeric"
  pattern="[0-9]{5}"
  maxlength="5"
  required
>
</label>

<label>
Clothing category
<select
  name="gender"
  required
>
<option value="">Choose one</option>
<option value="women">Womenswear</option>
<option value="men">Menswear</option>
<option value="neutral">Neutral</option>
</select>
</label>

<label>
Email address
<input
  type="email"
  name="email"
  maxlength="254"
  required
>
</label>

<button type="submit">
Build report
</button>

</form>
`
  );
}


function validateForm(
  body
) {
  const zip =
    String(
      body.zip || ''
    ).trim();

  const date =
    String(
      body.date || ''
    ).trim();

  const gender =
    String(
      body.gender || ''
    ).trim();

  const email =
    normalizeEmail(
      body.email
    );

  if (
    !/^\d{5}$/
      .test(zip)
  ) {
    return {
      error:
        'This service supports five-digit US ZIP codes only.',
    };
  }

  if (
    !realDate(date)
  ) {
    return {
      error:
        'Enter a valid calendar date.',
    };
  }

  if (
    !Object.prototype
      .hasOwnProperty.call(
        GENDERS,
        gender
      )
  ) {
    return {
      error:
        'Choose one of the available clothing categories.',
    };
  }

  if (
    !validEmail(email)
  ) {
    return {
      error:
        'Enter a valid email address.',
    };
  }

  return {
    zip:
      zip,
    date:
      date,
    gender:
      gender,
    email:
      email,
  };
}




function plainTextReport(
  report
) {
  function period(
    name,
    facts,
    advice
  ) {
    return [
      name.toUpperCase(),
      'Temperature: ' +
        facts.temperature.low_f +
        ' to ' +
        facts.temperature.high_f +
        ' F',
      'Wind: ' +
        facts.wind_speed.max_mph +
        ' mph',
      'Visibility: ' +
        facts.visibility.min_miles +
        ' miles',
      'UV: ' +
        facts.uv.max_index,
      'Humidity: ' +
        facts.humidity.average_percent +
        '%',
      'Rain: ' +
        facts.rain.category,
      'Snow: ' +
        facts.snow.category,
      'Road: ' +
        advice.road,
      'Dressing: ' +
        advice.dressing,
      'Accessories: ' +
        advice.accessories,
      '',
    ].join('\n');
  }

  return [
    'Weather Advisor Report',
    report.weather.city +
      ', ' +
      report.weather.state +
      ' ' +
      report.zip,
    'Date: ' +
      report.date,
    'Timezone: ' +
      report.weather.timezone,
    '',
    period(
      'Morning',
      report.weather
        .periods.morning,
      report.advice
        .morning
    ),
    period(
      'Night',
      report.weather
        .periods.night,
      report.advice
        .night
    ),
    'Advice source: ' +
      report.advice_source,
  ].join('\n');
}


function recipientKey(email) {
  return crypto
    .createHash('sha256')
    .update(
      normalizeEmail(email)
    )
    .digest('hex')
    .slice(0, 32);
}


async function sendReportEmail(
  email,
  report
) {
  if (!SNS_TOPIC_ARN) {
    throw new Error(
      'SNS_TOPIC_ARN_not_configured'
    );
  }

  const key =
    recipientKey(email);

  const subscription =
    await sns.send(
      new SubscribeCommand({
        TopicArn:
          SNS_TOPIC_ARN,

        Protocol:
          'email',

        Endpoint:
          email,

        Attributes: {
          FilterPolicy:
            JSON.stringify({
              recipient_key: [
                key,
              ],
            }),
        },

        ReturnSubscriptionArn:
          false,
      })
    );

  if (
    subscription.SubscriptionArn ===
    'pending confirmation'
  ) {
    return {
      status:
        'pending',
    };
  }

  await sns.send(
    new PublishCommand({
      TopicArn:
        SNS_TOPIC_ARN,

      Subject:
        'Weather Advisor Report ' +
        report.date,

      Message:
        plainTextReport(
          report
        ),

      MessageAttributes: {
        recipient_key: {
          DataType:
            'String',

          StringValue:
            key,
        },
      },
    })
  );

  return {
    status:
      'sent',
  };
}


app.get(
  '/',
  function (
    req,
    res
  ) {
    res.send(
      homePage()
    );
  }
);


app.get(
  '/health',
  function (
    req,
    res
  ) {
    res.json({
      status: 'ok',
    });
  }
);


app.post(
  '/report',
  async function (
    req,
    res
  ) {
    const input =
      validateForm(
        req.body
      );

    if (
      input.error
    ) {
      /*
      Validation happens before
      weather, Gemini, SES, or
      DynamoDB report calls.
      */
      return res
        .status(400)
        .send(
          homePage(
            input.error
          )
        );
    }

    const visitor =
      visitorId(req);

    if (
      !localRateLimit(
        visitorRequests,
        visitor,
        20,
        60 * 60 * 1000
      )
    ) {
      return res
        .status(429)
        .send(
          page(
            'Too many requests',
            '<h1>Too many requests</h1><p>Please try again later.</p>'
          )
        );
    }

    try {
      const result =
        await buildReport(
          input.zip,
          input.date,
          input.gender
        );

      if (
        result.status !==
        200
      ) {
        const message =
          (
            result.error &&
            result.error.message
          ) ||
          (
            result.error &&
            result.error.error
          ) ||
          'The report could not be created.';

        return res
          .status(
            result.status
          )
          .send(
            homePage(
              message
            )
          );
      }

      const report =
        result.report;

      const emailToken =
        Buffer.from(
          JSON.stringify({
            key:
              result.key,
            email:
              input.email,
          })
        ).toString(
          'base64url'
        );

      const body = `
<h1>Weather Advisor Report</h1>

<h2>
${escapeHtml(report.weather.city)},
${escapeHtml(report.weather.state)}
${escapeHtml(report.zip)}
</h2>

<p>
<strong>Date:</strong>
${escapeHtml(report.date)}
<br>
<strong>Local timezone:</strong>
${escapeHtml(report.weather.timezone)}
</p>

${reportTable(report)}

<p class="notice">
Advice source:
<strong>${escapeHtml(report.advice_source)}</strong>.
Weather measurements are shown from the weather data tier, not from Gemini.
</p>

<p>
Data attribution:
${report.weather.attribution
  .map(escapeHtml)
  .join(', ')}
</p>

<form
  method="POST"
  action="/email"
>
<input
  type="hidden"
  name="token"
  value="${escapeHtml(emailToken)}"
>

<button type="submit">
Email this report to ${escapeHtml(input.email)}
</button>
</form>

<p>
<a href="/">
Create another report
</a>
</p>
`;

      return res.send(
        page(
          'Weather Advisor Report',
          body
        )
      );
    } catch (err) {
      log(
        'report_error',
        {
          message:
            err.message,
        }
      );

      return res
        .status(503)
        .send(
          homePage(
            'The report service is temporarily unavailable. Please try again.'
          )
        );
    }
  }
);


app.post(
  '/email',
  async function (
    req,
    res
  ) {
    const visitor =
      visitorId(req);

    if (
      !localRateLimit(
        visitorEmails,
        visitor,
        EMAIL_LIMIT,
        60 * 60 * 1000
      )
    ) {
      return res
        .status(429)
        .send(
          page(
            'Email limit reached',
            '<h1>Email limit reached</h1><p>Please try again later.</p>'
          )
        );
    }

    let decoded;

    try {
      decoded =
        JSON.parse(
          Buffer.from(
            String(
              req.body.token ||
              ''
            ),
            'base64url'
          ).toString(
            'utf8'
          )
        );
    } catch (err) {
      return res
        .status(400)
        .send(
          page(
            'Invalid request',
            '<h1>Invalid email request</h1>'
          )
        );
    }

    const email =
      normalizeEmail(
        decoded.email
      );

    if (
      !validEmail(email) ||
      !decoded.key
    ) {
      return res
        .status(400)
        .send(
          page(
            'Invalid request',
            '<h1>Invalid email request</h1>'
          )
        );
    }

    const report =
      await getSavedReport(
        decoded.key
      );

    if (!report) {
      return res
        .status(410)
        .send(
          page(
            'Report expired',
            '<h1>Report expired</h1><p>Please create a new report.</p>'
          )
        );
    }

    try {
      const delivery =
        await sendReportEmail(
          email,
          report
        );

      if (
        delivery.status ===
        'pending'
      ) {
        return res.send(
          page(
            'Confirm email subscription',
            `
<h1>Check your inbox</h1>
<p>
Amazon SNS sent a confirmation message to
<strong>${escapeHtml(email)}</strong>.
</p>
<p>
Click the confirmation link in that email, then return to your report and click the email button again.
</p>
<p>
This confirmation is required before Weather Advisor can send reports to that address.
</p>
`
          )
        );
      }

      return res.send(
        page(
          'Report sent',
          `
<h1>Report sent</h1>
<p>
The Weather Advisor report was published only to the confirmed subscription for
<strong>${escapeHtml(email)}</strong>.
</p>
<p>
<a href="/">Create another report</a>
</p>
`
        )
      );
    } catch (err) {
      log(
        'email_error',
        {
          message:
            err.message,
        }
      );

      return res
        .status(503)
        .send(
          page(
            'Email unavailable',
            `
<h1>Email could not be sent</h1>
<p>
The email service did not accept the request.
</p>
<p>
<small>${escapeHtml(err.name || 'Error')}: ${escapeHtml(err.message || '')}</small>
</p>
`
          )
        );
    }
  }
);


app.listen(
  PORT,
  function () {
    log(
      'advisor_started',
      {
        port:
          PORT,

        model:
          GEMINI_MODEL,

        table:
          ADVISOR_TABLE,
      }
    );
  }
);
