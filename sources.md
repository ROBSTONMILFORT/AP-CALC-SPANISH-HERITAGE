# Sources and indicator reference

## Primary data source

All historical values are retrieved from the official World Bank Indicators API:

- API documentation: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
- World Bank Open Data: https://data.worldbank.org/
- API endpoint pattern: `https://api.worldbank.org/v2/country/{ISO3}/indicator/{INDICATOR_CODE}?format=json&date={START}:{END}`

The application requests the period from the current calendar year minus 70 through the previous calendar year, inclusive. It reports actual non-null numeric coverage and observation count. The retrieval date is recorded in the interface and exports. API observations may be revised by the World Bank.

## Supported countries

| Display name | World Bank country code |
|---|---|
| Mexico (MX) | MEX |
| Brazil (BR) | BRA |
| Argentina (AR) | ARG |
| Colombia (CO) | COL |
| Chile (CL) | CHL |
| Peru (PE) | PER |
| Venezuela (VE) | VEN |
| Ecuador (EC) | ECU |
| Uruguay (UY) | URY |

Brazil is included as a Latin American comparison country. Portuguese is its official language; it is not a Spanish-speaking country and is not Hispanic in the narrow cultural/linguistic sense.

## Indicator mappings and interpretation

| Indicator | World Bank code | Unit | Interpretation / caution |
|---|---|---|---|
| Life expectancy at birth | `SP.DYN.LE00.IN` | years | Population life-table estimate; not an individual lifespan prediction. |
| Unemployment, national estimate | `SL.UEM.TOTL.NE.ZS` | % of total labor force | National estimates may use methods that differ across countries. |
| GDP per capita | `NY.GDP.PCAP.CD` | current US$ per person | GDP divided by midyear population. Not average wealth or household income; current dollars reflect exchange rates and prices. |
| Crude birth rate | `SP.DYN.CBRT.IN` | births per 1,000 people per year | A rate, not a total birth count. |
| Net migration | `SM.POP.NETM` | people (net estimate) | Net migration is not an emigration count and does not reveal gross arrivals/departures separately. |
| Intentional homicide rate | `VC.IHR.PSRC.P5` | intentional homicides per 100,000 people | Recording practices and data completeness may differ. |
| Consumer price inflation | `FP.CPI.TOTL.ZG` | % annual change | Inflation rate can be negative during deflation; it is not the price index level. |
| Central government debt | `GC.DOD.TOTL.GD.ZS` | % of GDP | Central government measure; not necessarily all public-sector liabilities. |
| Total reserves including gold | `FI.RES.TOTL.CD` | current US dollars | Includes monetary gold, SDRs, IMF reserve positions, and foreign exchange. Nominal values are affected by valuation/exchange rates. |
| External balance on goods and services | `NE.RSB.GNFS.ZS` | % of GDP | Exports less imports of goods/services as % GDP. Not the full current-account balance. |

## API behavior

The API returns JSON. The app requests a date range and reads the observation `date` and `value` fields. Null values are excluded from the numeric modeling table and are not filled, interpolated, or replaced with synthetic values. If a request times out, fails, or returns no usable observations, the app displays an error and stops the analysis for that selection.

## Model references and caveats

The polynomial is fit with centered time, `t = year - base year`. Fit metrics are computed against the same observations used for fitting and are explicitly labeled in-sample. The optional chronological holdout reserves the latest portion of the observations for a separate check when at least degree + 1 training observations remain.

The app does not calculate or label simplified error bounds as 95% prediction intervals. Residuals and MAE are descriptive measures of historical model error, not inferential intervals. Polynomial extrapolation is especially uncertain and may produce implausible values.
