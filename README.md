# Hispanic Heritage Historical Data Explorer

A Streamlit classroom application that retrieves authentic historical indicators from the World Bank API, validates an editable working copy, fits centered-time polynomial models, compares countries, and exports CSV, Excel, and PDF reports.

## Research setup

The sidebar contains editable fields for the team's research question, featured country, indicator, mathematics pathway, polynomial degree, graph sample increment, forward display horizon, comparison country, and printer-friendly view.

**Before presenting:** replace the default research question with your team's approved question and select your assigned country, indicator, and pathway. Brazil is included as a Latin American comparison country. It is not Spanish-speaking and is not Hispanic in the narrow linguistic/cultural sense.

## Included files

- `app.py` — complete Streamlit application.
- `requirements.txt` — pinned Python package versions.
- `sources.md` — World Bank indicator references, definitions, and data caveats.

## Run locally

Use Python 3.10–3.12 (recommended: Python 3.11).

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python -m streamlit run app.py
```

The app uses the public World Bank API; no API key or credentials are required. Network access is required to retrieve data. Requests are cached for one hour.

**Verification status:** `app.py` passed Python syntax compilation in the file-generation environment. The live Streamlit interface, external World Bank requests, and download workflows were not executed end-to-end here. The pinned package versions below are the intended compatible environment; install them and complete the verification checklist before presenting the app as fully tested.

## GitHub setup

1. Create a GitHub repository, for example `hispanic-heritage-data-explorer`.
2. Add `app.py`, `requirements.txt`, `README.md`, and `sources.md` to the repository root.
3. Commit and push the files.
4. Do not commit passwords, tokens, private data, or `.env` files. This app does not require credentials.

## Streamlit Community Cloud

1. Sign in to Streamlit Community Cloud and connect GitHub.
2. Select the repository and branch.
3. Set the app's main file path to `app.py`.
4. Deploy. Community Cloud installs packages from `requirements.txt`.
5. If deployment fails, open the app's logs. Check the Python version, dependency installation, and whether the selected repository branch contains all four files.

## Render deployment

Create a **Python Web Service** connected to the GitHub repository.

- Build command:

```bash
pip install -r requirements.txt
```

- Start command (one line):

```bash
python -m streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT
```

Do not split the start command across separate Render command fields. Render supplies `$PORT`. Review deploy logs if the service exits or reports a port-binding error.

## Verification checklist

### Data source and labels
- [ ] Confirm the country code and indicator code shown in the app match `sources.md`.
- [ ] Open the World Bank source link and compare several year/value pairs.
- [ ] Confirm retrieval date, requested year window, actual year coverage, and non-null count.
- [ ] Confirm missing values remain missing; the app does not invent or interpolate observations.
- [ ] Confirm GDP per capita is not described as average wealth or household income.
- [ ] Confirm crude birth rate is a rate, not a birth count.
- [ ] Confirm net migration is a net estimate, not an emigration count.

### Editing and validation
- [ ] Change a value in the working table. Confirm the app labels the result a **USER-MODIFIED SCENARIO**.
- [ ] Press **Reset to source** and confirm the original values return.
- [ ] Add a duplicate year and confirm validation blocks the model.
- [ ] Enter a decimal year, blank value, nonnumeric value, or prohibited negative value and confirm a useful validation message.
- [ ] Delete rows until fewer than degree + 1 distinct years remain; confirm the model is blocked.

### Mathematics
- [ ] Confirm `t = year - base year` and the displayed base year.
- [ ] Compare the polynomial's fitted values against the residual table.
- [ ] Check R², MAE, RMSE, mean, and observation count. They are labeled in-sample.
- [ ] If enough data exist, confirm the latest chronological observations are reserved for a separately labeled holdout test.
- [ ] Calculate a year with the single-year control and then include the same year in batch mode. The estimates should agree to displayed precision.
- [ ] Test custom batch input with valid years, a malformed token, an out-of-range year, and duplicate years.
- [ ] For Calculus, inspect derivative roots, endpoints, critical-point classifications, and inflection checks.

### Controls and exports
- [ ] Change country and indicator; confirm the source and units change.
- [ ] Change degree; confirm equation and fit metrics change.
- [ ] Change graph sample increment; confirm model sample markers change.
- [ ] Change forward display horizon; confirm the displayed extrapolated segment changes.
- [ ] Change comparison country; confirm its same-indicator series and coverage note change.
- [ ] Toggle printer-friendly view; confirm the simplified report panel appears.
- [ ] Download CSV and inspect the current working table.
- [ ] Download `.xlsx` and confirm Summary, Working Data, and Calculated Years sheets.
- [ ] Download PDF and confirm metadata, equation, metrics, chart, findings/limitations, data preview, and calculated results are present.

### API and deployment
- [ ] Test another country/indicator if the API returns no observations for one selection.
- [ ] If an API error occurs, confirm the app shows the error and does not substitute random data.
- [ ] Test the deployed app from a browser separate from the developer's session.

## Common errors and diagnosis

- **`ModuleNotFoundError`:** dependency installation failed or the package is missing from `requirements.txt`. Read the build log and redeploy.
- **`requests` timeout / API error:** check the World Bank API status, network access, and logs. Retry later; no synthetic data are substituted.
- **No observations:** the API may have null values for the selected indicator/country/period. Try another supported selection and report the actual coverage.
- **Not enough observations:** lower the polynomial degree or choose a selection with more non-null years. Never pad the dataset with invented observations.
- **Duplicate years / invalid values:** fix the editable table or reset it to source.
- **Render port error:** verify the exact single-line start command and that `$PORT` is used.
- **PDF/Excel download error:** inspect the Streamlit traceback and confirm ReportLab/XlsxWriter installed successfully.

## How the app works

1. **Retrieve:** `fetch_world_bank()` calls the World Bank API for the selected country and indicator. It requests current year − 70 through current year − 1. It preserves only non-null numeric observations and caches successful or empty responses for one hour.
2. **Separate source and working data:** the original API result is retained independently from the editable table. Reset restores the source. Editing marks the run as a user-modified scenario.
3. **Validate:** `validate_working_data()` checks integer years, duplicate years, numeric finite values, and broad indicator-specific sign/range rules.
4. **Fit:** `fit_polynomial()` uses centered time, `t = year - base year`, and a polynomial of the selected degree. At least degree + 1 distinct years are required.
5. **Evaluate:** the same centered transformation is used for all single-year and batch estimates. Estimates outside the observed interval are extrapolations and are flagged when they violate broad plausibility checks.
6. **Analyze:** residuals and in-sample fit metrics summarize model fit. A chronological holdout score is shown separately when sufficient training data remain. Calculus mode evaluates derivatives and checks extrema/inflection points over the observed interval.
7. **Visualize and export:** the chart distinguishes observations, historical fit, extrapolation, sample markers, and calculated estimates. Export functions create actual CSV, XLSX, and PDF files from the current selection.

## Mathematical assumptions and limitations

- A polynomial is a descriptive curve fit, not a causal explanation.
- Centering time improves numerical conditioning and makes the intercept correspond to the model value at the base year.
- Higher degree can create extra turning points and unstable extrapolation. A high in-sample R² does not establish predictive accuracy.
- MAE/RMSE describe residual size on the fitted observations. They are not 95% prediction intervals.
- The chronological holdout is a small out-of-sample check, not a guarantee of future performance.
- World Bank observations can be revised, estimated, missing, or methodologically different across countries. National-estimate unemployment and other indicators may not be perfectly comparable.
- Country comparisons may have different coverage. The app does not interpolate missing observations.
- A broad plausibility flag is a warning, not a proof that a value is impossible.
- The model does not include explanatory variables or prove why an indicator changed.
