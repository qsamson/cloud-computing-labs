const express = require('express');

const {
  DynamoDBClient,
} = require('@aws-sdk/client-dynamodb');

const {
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
} = require('@aws-sdk/lib-dynamodb');


const app = express();

const PORT = Number(process.env.PORT || 3000);

const ZIP_API =
  process.env.ZIP_API_BASE ||
  'https://api.zippopotam.us';

const NWS_API =
  process.env.NWS_API_BASE ||
  'https://api.weather.gov';

const OPEN_METEO_API =
  process.env.OPEN_METEO_API_BASE ||
  'https://api.open-meteo.com/v1/forecast';

const USER_AGENT =
  process.env.NWS_USER_AGENT ||
  '(ITMO 544 Weather Advisor, student@example.com)';

const FACTS_TABLE =
  process.env.FACTS_TABLE ||
  'weather-advisor-facts';

const CACHE_SECONDS =
  Number(process.env.CACHE_SECONDS || 900);

const STALE_SECONDS =
  Number(process.env.STALE_SECONDS || 21600);


const ddb = DynamoDBDocumentClient.from(
  new DynamoDBClient({
    region: process.env.AWS_REGION,
  })
);


const log = (event, fields = {}) => {
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      event,
      ...fields,
    })
  );
};


class UpstreamError extends Error {
  constructor(stage, status = 0) {
    super(`${stage} failed`);
    this.stage = stage;
    this.status = status;
  }
}


async function fetchJson(
  stage,
  url,
  headers = {}
) {
  let status = 0;

  for (
    let attempt = 1;
    attempt <= 2;
    attempt++
  ) {
    try {
      const response = await fetch(
        url,
        {
          headers,
          signal:
            AbortSignal.timeout(
              8000
            ),
        }
      );

      status = response.status;

      if (response.ok) {
        return await response.json();
      }

      if (response.status === 404) {
        return null;
      }

      if (
        response.status < 500 &&
        response.status !== 429
      ) {
        break;
      }
    } catch (err) {
      status = 0;
    }

    if (attempt < 2) {
      await new Promise(
        resolve =>
          setTimeout(resolve, 500)
      );
    }
  }

  throw new UpstreamError(
    stage,
    status
  );
}


function round(value, digits = 1) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
    return null;
  }

  const factor =
    10 ** digits;

  return (
    Math.round(
      Number(value) * factor
    ) / factor
  );
}


function mean(values) {
  const good =
    values.filter(
      value =>
        Number.isFinite(
          Number(value)
        )
    );

  if (!good.length) {
    return null;
  }

  return (
    good.reduce(
      (sum, value) =>
        sum + Number(value),
      0
    ) / good.length
  );
}


function sum(values) {
  return values
    .filter(
      value =>
        Number.isFinite(
          Number(value)
        )
    )
    .reduce(
      (total, value) =>
        total + Number(value),
      0
    );
}


function maximum(values) {
  const good =
    values
      .map(Number)
      .filter(Number.isFinite);

  return good.length
    ? Math.max(...good)
    : null;
}


function minimum(values) {
  const good =
    values
      .map(Number)
      .filter(Number.isFinite);

  return good.length
    ? Math.min(...good)
    : null;
}


function isRealDate(dateText) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(
      dateText
    )
  ) {
    return false;
  }

  const date =
    new Date(
      `${dateText}T00:00:00Z`
    );

  return (
    !Number.isNaN(
      date.getTime()
    ) &&
    date
      .toISOString()
      .slice(0, 10) ===
      dateText
  );
}


function addDays(dateText, days) {
  const date =
    new Date(
      `${dateText}T00:00:00Z`
    );

  date.setUTCDate(
    date.getUTCDate() + days
  );

  return date
    .toISOString()
    .slice(0, 10);
}


function zonedParts(
  date,
  timeZone
) {
  const formatter =
    new Intl.DateTimeFormat(
      'en-CA',
      {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        hourCycle: 'h23',
      }
    );

  const parts = {};

  for (
    const part of
    formatter.formatToParts(
      date
    )
  ) {
    if (part.type !== 'literal') {
      parts[part.type] =
        part.value;
    }
  }

  return {
    date:
      `${parts.year}-` +
      `${parts.month}-` +
      `${parts.day}`,
    hour:
      Number(parts.hour),
  };
}


function todayInZone(
  timeZone
) {
  return zonedParts(
    new Date(),
    timeZone
  ).date;
}


function periodNameForHour(
  hour
) {
  if (
    hour >= 6 &&
    hour <= 11
  ) {
    return 'morning';
  }

  if (
    hour >= 18 &&
    hour <= 23
  ) {
    return 'night';
  }

  return null;
}


function parseWindMph(
  windSpeed
) {
  if (!windSpeed) {
    return null;
  }

  if (
    /calm/i.test(windSpeed)
  ) {
    return 0;
  }

  const numbers =
    String(windSpeed)
      .match(/\d+(\.\d+)?/g);

  if (!numbers) {
    return null;
  }

  return Math.max(
    ...numbers.map(Number)
  );
}


function mostCommon(values) {
  const counts =
    new Map();

  for (
    const value of values
  ) {
    if (!value) {
      continue;
    }

    counts.set(
      value,
      (counts.get(value) || 0) +
        1
    );
  }

  let best = null;
  let bestCount = 0;

  for (
    const [
      value,
      count,
    ] of counts
  ) {
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }

  return best;
}


/*
Rain categories use the National Weather Service
rainfall-rate convention:

No    = 0
Mild  = >0 through 0.30 inch/hour
Heavy = >0.30 inch/hour

The project's "Mild" category combines the NWS
light and moderate ranges.
*/
function rainCategory(
  maxHourlyRain,
  probability
) {
  if (
    maxHourlyRain !== null &&
    maxHourlyRain > 0.30
  ) {
    return 'Heavy';
  }

  if (
    maxHourlyRain !== null &&
    maxHourlyRain > 0
  ) {
    return 'Mild';
  }

  /*
  If the amount model is zero but precipitation
  probability is high, report Mild instead of
  incorrectly claiming "No" precipitation.
  */
  if (
    probability !== null &&
    probability >= 50
  ) {
    return 'Mild';
  }

  return 'No';
}


/*
For the project categories, snow at or above
1 inch/hour is considered Heavy. Any measurable
snow below that rate is Mild.
*/
function snowCategory(
  maxHourlySnow
) {
  if (
    maxHourlySnow !== null &&
    maxHourlySnow >= 1
  ) {
    return 'Heavy';
  }

  if (
    maxHourlySnow !== null &&
    maxHourlySnow > 0
  ) {
    return 'Mild';
  }

  return 'No';
}


function cacheKey(
  zip,
  date
) {
  return `facts#${zip}#${date}`;
}


async function readCache(
  zip,
  date
) {
  try {
    const response =
      await ddb.send(
        new GetCommand({
          TableName:
            FACTS_TABLE,
          Key: {
            cache_key:
              cacheKey(
                zip,
                date
              ),
          },
        })
      );

    return (
      response.Item ||
      null
    );
  } catch (err) {
    log(
      'cache_read_error',
      {
        message:
          err.message,
      }
    );

    return null;
  }
}


async function writeCache(
  zip,
  date,
  payload
) {
  const now =
    Math.floor(
      Date.now() / 1000
    );

  try {
    await ddb.send(
      new PutCommand({
        TableName:
          FACTS_TABLE,

        Item: {
          cache_key:
            cacheKey(
              zip,
              date
            ),

          zip,
          date,

          payload,

          created_at:
            now,

          fresh_until:
            now +
            CACHE_SECONDS,

          expires_at:
            now +
            STALE_SECONDS,
        },
      })
    );

    return true;
  } catch (err) {
    log(
      'cache_write_error',
      {
        message:
          err.message,
      }
    );

    return false;
  }
}


async function lookupZip(
  zip
) {
  const lookup =
    await fetchJson(
      'zip_lookup',
      `${ZIP_API}/us/${zip}`
    );

  if (
    !lookup ||
    !lookup.places ||
    !lookup.places.length
  ) {
    return null;
  }

  const place =
    lookup.places[0];

  return {
    city:
      place[
        'place name'
      ],

    state:
      place[
        'state abbreviation'
      ],

    latitude:
      Number(
        place.latitude
      ),

    longitude:
      Number(
        place.longitude
      ),
  };
}


async function getNwsHourly(
  latitude,
  longitude
) {
  const headers = {
    'User-Agent':
      USER_AGENT,

    Accept:
      'application/geo+json',
  };

  const lat =
    Number(latitude)
      .toFixed(4);

  const lon =
    Number(longitude)
      .toFixed(4);

  const point =
    await fetchJson(
      'nws_points',
      `${NWS_API}/points/${lat},${lon}`,
      headers
    );

  if (
    !point ||
    !point.properties ||
    !point.properties
      .forecastHourly
  ) {
    return null;
  }

  const forecast =
    await fetchJson(
      'nws_hourly',
      point.properties
        .forecastHourly,
      headers
    );

  if (
    !forecast ||
    !forecast.properties
  ) {
    return null;
  }

  return (
    forecast.properties
      .periods || []
  );
}


async function getOpenMeteo(
  latitude,
  longitude
) {
  const hourly = [
    'temperature_2m',
    'apparent_temperature',
    'relative_humidity_2m',
    'precipitation_probability',
    'rain',
    'snowfall',
    'visibility',
    'wind_speed_10m',
    'wind_gusts_10m',
    'uv_index',
  ].join(',');

  const params =
    new URLSearchParams({
      latitude:
        String(latitude),

      longitude:
        String(longitude),

      hourly,

      temperature_unit:
        'fahrenheit',

      wind_speed_unit:
        'mph',

      precipitation_unit:
        'inch',

      timezone:
        'auto',

      /*
      Unix time is intentional.
      We convert it with the returned
      IANA timezone so DST is handled
      by JavaScript.
      */
      timeformat:
        'unixtime',

      forecast_days:
        '8',
    });

  return await fetchJson(
    'open_meteo',
    `${OPEN_METEO_API}?${params}`
  );
}


function openMeteoRecords(data) {
  const hourly = data.hourly || {};
  const times = hourly.time || [];

  function valueAt(name, index) {
    const values = hourly[name];
    return Array.isArray(values)
      ? values[index]
      : null;
  }

  return times.map(
    (time, index) => ({
      time: Number(time),

      temperature:
        valueAt(
          'temperature_2m',
          index
        ),

      apparentTemperature:
        valueAt(
          'apparent_temperature',
          index
        ),

      humidity:
        valueAt(
          'relative_humidity_2m',
          index
        ),

      precipitationProbability:
        valueAt(
          'precipitation_probability',
          index
        ),

      rain:
        valueAt(
          'rain',
          index
        ),

      snowfall:
        valueAt(
          'snowfall',
          index
        ),

      visibility:
        valueAt(
          'visibility',
          index
        ),

      windSpeed:
        valueAt(
          'wind_speed_10m',
          index
        ),

      windGust:
        valueAt(
          'wind_gusts_10m',
          index
        ),

      uvIndex:
        valueAt(
          'uv_index',
          index
        ),
    })
  );
}


function selectOpenPeriod(
  records,
  dateText,
  timeZone,
  periodName
) {
  return records.filter(
    record => {
      const local =
        zonedParts(
          new Date(
            record.time *
              1000
          ),
          timeZone
        );

      return (
        local.date ===
          dateText &&
        periodNameForHour(
          local.hour
        ) === periodName
      );
    }
  );
}


function selectNwsPeriod(
  periods,
  dateText,
  timeZone,
  periodName
) {
  return periods.filter(
    period => {
      const local =
        zonedParts(
          new Date(
            period.startTime
          ),
          timeZone
        );

      return (
        local.date ===
          dateText &&
        periodNameForHour(
          local.hour
        ) === periodName
      );
    }
  );
}


function buildPeriodFacts(
  periodName,
  nwsPeriods,
  openPeriods
) {
  const nwsTemps =
    nwsPeriods.map(
      item =>
        item.temperature
    );

  const openTemps =
    openPeriods.map(
      item =>
        item.temperature
    );

  const temperatures =
    nwsTemps.length
      ? nwsTemps
      : openTemps;

  const temperatureSource =
    nwsTemps.length
      ? 'National Weather Service hourly forecast'
      : 'Open-Meteo fallback';

  const nwsWind =
    nwsPeriods
      .map(
        item =>
          parseWindMph(
            item.windSpeed
          )
      )
      .filter(
        value =>
          value !== null
      );

  const openWind =
    openPeriods.map(
      item =>
        item.windSpeed
    );

  const windValues =
    nwsWind.length
      ? nwsWind
      : openWind;

  const windSource =
    nwsWind.length
      ? 'National Weather Service hourly forecast'
      : 'Open-Meteo fallback';

  const nwsProbability =
    nwsPeriods
      .map(
        item =>
          item.probabilityOfPrecipitation
          ? item.probabilityOfPrecipitation.value
          : null
      )
      .filter(
        value =>
          value !== null &&
          value !== undefined
      );

  const openProbability =
    openPeriods.map(
      item =>
        item
          .precipitationProbability
    );

  const precipitationProbability =
    maximum(
      nwsProbability.length
        ? nwsProbability
        : openProbability
    );

  const rainValues =
    openPeriods.map(
      item =>
        item.rain
    );

  const snowValues =
    openPeriods.map(
      item =>
        item.snowfall
    );

  const maxHourlyRain =
    maximum(
      rainValues
    );

  const maxHourlySnow =
    maximum(
      snowValues
    );

  const visibilityMeters =
    openPeriods.map(
      item =>
        item.visibility
    );

  const minVisibilityMeters =
    minimum(
      visibilityMeters
    );

  const conditions =
    mostCommon(
      nwsPeriods.map(
        item =>
          item.shortForecast
      )
    );

  return {
    period:
      periodName,

    hours:
      periodName ===
        'morning'
        ? '06:00-11:59'
        : '18:00-23:59',

    temperature: {
      available:
        temperatures.length >
        0,

      low_f:
        round(
          minimum(
            temperatures
          ),
          1
        ),

      high_f:
        round(
          maximum(
            temperatures
          ),
          1
        ),

      average_f:
        round(
          mean(
            temperatures
          ),
          1
        ),

      apparent_average_f:
        round(
          mean(
            openPeriods.map(
              item =>
                item
                  .apparentTemperature
            )
          ),
          1
        ),

      source:
        temperatureSource,
    },

    wind_speed: {
      available:
        windValues.length >
        0,

      max_mph:
        round(
          maximum(
            windValues
          ),
          1
        ),

      max_gust_mph:
        round(
          maximum(
            openPeriods.map(
              item =>
                item.windGust
            )
          ),
          1
        ),

      direction:
        mostCommon(
          nwsPeriods.map(
            item =>
              item.windDirection
          )
        ),

      source:
        windSource,
    },

    visibility: {
      available:
        minVisibilityMeters !==
        null,

      min_miles:
        minVisibilityMeters ===
        null
          ? null
          : round(
              minVisibilityMeters /
                1609.344,
              1
            ),

      source:
        'Open-Meteo hourly visibility',
    },

    uv: {
      available:
        maximum(
          openPeriods.map(
            item =>
              item.uvIndex
          )
        ) !== null,

      max_index:
        round(
          maximum(
            openPeriods.map(
              item =>
                item.uvIndex
          )
        ),
        1
      ),

      source:
        'Open-Meteo hourly UV index',
    },

    humidity: {
      available:
        openPeriods.length >
        0,

      average_percent:
        round(
          mean(
            openPeriods.map(
              item =>
                item.humidity
            )
          ),
          1
        ),

      source:
        'Open-Meteo hourly relative humidity',
    },

    rain: {
      category:
        rainCategory(
          maxHourlyRain,
          precipitationProbability
        ),

      total_inches:
        round(
          sum(
            rainValues
          ),
          2
        ),

      max_hourly_inches:
        round(
          maxHourlyRain,
          2
        ),

      max_probability_percent:
        round(
          precipitationProbability,
          0
        ),

      source:
        'Open-Meteo amount + NWS precipitation probability',
    },

    snow: {
      category:
        snowCategory(
          maxHourlySnow
        ),

      total_inches:
        round(
          sum(
            snowValues
          ),
          2
        ),

      max_hourly_inches:
        round(
          maxHourlySnow,
          2
        ),

      source:
        'Open-Meteo hourly snowfall',
    },

    short_forecast:
      conditions ||
      'Not available',
  };
}


async function buildFacts(
  zip,
  dateText
) {
  const location =
    await lookupZip(zip);

  if (!location) {
    return {
      status: 404,
      error: {
        error:
          'zip_not_found',

        message:
          'ZIP code not found.',
      },
    };
  }

  const openMeteo =
    await getOpenMeteo(
      location.latitude,
      location.longitude
    );

  if (
    !openMeteo ||
    !openMeteo.timezone
  ) {
    throw new UpstreamError(
      'open_meteo'
    );
  }

  const timeZone =
    openMeteo.timezone;

  const today =
    todayInZone(
      timeZone
    );

  const lastAllowed =
    addDays(
      today,
      6
    );

  if (
    dateText < today ||
    dateText >
      lastAllowed
  ) {
    return {
      status: 400,

      error: {
        error:
          'date_out_of_range',

        message:
          `Date must be between ${today} and ${lastAllowed} in the location's local time.`,
      },
    };
  }

  let nwsPeriods = [];

  try {
    nwsPeriods =
      (
        await getNwsHourly(
          location.latitude,
          location.longitude
        )
      ) || [];
  } catch (err) {
    log(
      'nws_error',
      {
        zip,
        message:
          err.message,
      }
    );
  }

  const openRecords =
    openMeteoRecords(
      openMeteo
    );

  const morning =
    buildPeriodFacts(
      'morning',

      selectNwsPeriod(
        nwsPeriods,
        dateText,
        timeZone,
        'morning'
      ),

      selectOpenPeriod(
        openRecords,
        dateText,
        timeZone,
        'morning'
      )
    );

  const night =
    buildPeriodFacts(
      'night',

      selectNwsPeriod(
        nwsPeriods,
        dateText,
        timeZone,
        'night'
      ),

      selectOpenPeriod(
        openRecords,
        dateText,
        timeZone,
        'night'
      )
    );

  return {
    status: 200,

    payload: {
      zip,

      date:
        dateText,

      city:
        location.city,

      state:
        location.state,

      latitude:
        location.latitude,

      longitude:
        location.longitude,

      timezone:
        timeZone,

      periods: {
        morning,
        night,
      },

      attribution: [
        'National Weather Service',
        'Open-Meteo',
        'Zippopotam.us',
      ],
    },
  };
}


app.get(
  '/',
  (req, res) => {
    res.json({
      service:
        'weather-data',

      usage:
        '/weather?zip=60616&date=YYYY-MM-DD',

      periods: {
        morning:
          '06:00-11:59 local time',

        night:
          '18:00-23:59 local time',
      },
    });
  }
);


app.get(
  '/health',
  (req, res) => {
    res.json({
      status: 'ok',
    });
  }
);


app.get(
  '/weather',
  async (req, res) => {
    const zip =
      String(
        req.query.zip ||
        ''
      ).trim();

    const dateText =
      String(
        req.query.date ||
        ''
      ).trim();

    /*
    Reject malformed ZIP codes before
    making ANY outside request.
    */
    if (
      !/^\d{5}$/.test(
        zip
      )
    ) {
      return res
        .status(400)
        .json({
          error:
            'invalid_zip',

          message:
            'This service supports five-digit US ZIP codes only.',
        });
    }

    /*
    Impossible or malformed dates are
    also rejected locally.
    */
    if (
      !isRealDate(
        dateText
      )
    ) {
      return res
        .status(400)
        .json({
          error:
            'invalid_date',

          message:
            'Enter a real date in YYYY-MM-DD format.',
        });
    }

    const started =
      Date.now();

    const now =
      Math.floor(
        Date.now() /
        1000
      );

    const cached =
      await readCache(
        zip,
        dateText
      );

    if (
      cached &&
      cached.payload &&
      cached.fresh_until >
        now
    ) {
      return res.json({
        ...cached.payload,

        cache:
          'hit',

        cache_age_seconds:
          Math.max(
            0,
            now -
              cached.created_at
          ),
      });
    }

    try {
      const result =
        await buildFacts(
          zip,
          dateText
        );

      if (
        result.status !==
        200
      ) {
        return res
          .status(
            result.status
          )
          .json(
            result.error
          );
      }

      const saved =
        await writeCache(
          zip,
          dateText,
          result.payload
        );

      log(
        'weather_success',
        {
          zip,
          date:
            dateText,

          ms:
            Date.now() -
            started,
        }
      );

      return res.json({
        ...result.payload,

        cache:
          saved
            ? 'miss'
            : 'unavailable',
      });
    } catch (err) {
      /*
      Required degraded behavior:
      use a recent stale cached copy
      rather than invent weather data.
      */
      if (
        cached &&
        cached.payload &&
        cached.expires_at >
          now
      ) {
        log(
          'weather_stale_cache',
          {
            zip,
            date:
              dateText,
          }
        );

        return res.json({
          ...cached.payload,

          cache:
            'stale',

          warning:
            'Live weather data is temporarily unavailable. Showing a recent cached forecast.',

          cache_age_seconds:
            Math.max(
              0,
              now -
                cached.created_at
            ),
        });
      }

      log(
        'weather_error',
        {
          zip,
          date:
            dateText,

          stage:
            err.stage ||
            'internal',

          status:
            err.status ||
            0,

          message:
            err.message,
        }
      );

      return res
        .status(503)
        .json({
          error:
            'weather_data_unavailable',

          message:
            'Weather data is temporarily unavailable. Please try again later.',
        });
    }
  }
);


app.listen(
  PORT,
  () => {
    log(
      'weather_started',
      {
        port:
          PORT,

        facts_table:
          FACTS_TABLE,
      }
    );
  }
);
