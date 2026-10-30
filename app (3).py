from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any
import math
import re
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st
from sklearn.metrics import mean_absolute_error, mean_squared_error
from numpy.polynomial import Polynomial
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)

APP_TITLE = "Hispanic Heritage Historical Data Explorer"
COUNTRIES = {
    "Mexico (MX)": "MEX", "Brazil (BR)": "BRA", "Argentina (AR)": "ARG",
    "Colombia (CO)": "COL", "Chile (CL)": "CHL", "Peru (PE)": "PER",
    "Venezuela (VE)": "VEN", "Ecuador (EC)": "ECU", "Uruguay (UY)": "URY",
}
INDICATORS = {
    "Life expectancy at birth": {
        "code": "SP.DYN.LE00.IN", "unit": "years",
        "definition": "The number of years a newborn would live if patterns of mortality at the time of birth remained the same.",
        "constraint": "positive",
        "caveat": "This is a population-level life-table estimate, not a prediction for an individual."
    },
    "Unemployment, national estimate": {
        "code": "SL.UEM.TOTL.NE.ZS", "unit": "% of total labor force",
        "definition": "The share of the labor force without work but available for and seeking employment, using national estimates.",
        "constraint": "percent",
        "caveat": "National estimates can use country-specific methods and may not be perfectly comparable."
    },
    "GDP per capita": {
        "code": "NY.GDP.PCAP.CD", "unit": "current US$ per person",
        "definition": "Gross domestic product divided by the midyear population, expressed in current US dollars.",
        "constraint": "nonnegative",
        "caveat": "GDP per capita is not average wealth or household income. Current-dollar values are affected by prices and exchange rates."
    },
    "Crude birth rate": {
        "code": "SP.DYN.CBRT.IN", "unit": "births per 1,000 people per year",
        "definition": "The annual number of live births per 1,000 people in the population.",
        "constraint": "nonnegative",
        "caveat": "This is a rate, not a total birth count."
    },
    "Net migration": {
        "code": "SM.POP.NETM", "unit": "people (net estimate)",
        "definition": "The net total of migrants during a period: immigrants minus emigrants, including adjustments.",
        "constraint": "any",
        "caveat": "A net estimate is not an emigration count and does not show gross flows in each direction."
    },
    "Intentional homicide rate": {
        "code": "VC.IHR.PSRC.P5", "unit": "intentional homicides per 100,000 people",
        "definition": "Victims of intentional homicide per 100,000 population.",
        "constraint": "nonnegative",
        "caveat": "Definitions, recording practices, and data completeness can differ across countries and years."
    },
    "Consumer price inflation": {
        "code": "FP.CPI.TOTL.ZG", "unit": "% annual change",
        "definition": "The annual percentage change in the cost to the average consumer of acquiring a basket of goods and services.",
        "constraint": "any",
        "caveat": "Inflation can be negative during deflation; it is not the price level itself."
    },
    "Central government debt": {
        "code": "GC.DOD.TOTL.GD.ZS", "unit": "% of GDP",
        "definition": "Central government debt as a percentage of gross domestic product.",
        "constraint": "nonnegative",
        "caveat": "Coverage is central government, not necessarily all public-sector liabilities."
    },
    "Total reserves including gold": {
        "code": "FI.RES.TOTL.CD", "unit": "current US dollars",
        "definition": "Holdings of monetary gold, special drawing rights, reserve positions in the IMF, and foreign exchange reserves.",
        "constraint": "nonnegative",
        "caveat": "Nominal dollar amounts are affected by valuation and exchange-rate changes."
    },
    "External balance on goods and services": {
        "code": "NE.RSB.GNFS.ZS", "unit": "% of GDP",
        "definition": "Exports of goods and services minus imports of goods and services, expressed as a percentage of GDP.",
        "constraint": "any",
        "caveat": "A positive value is a surplus; a negative value is a deficit. This is not the full current-account balance."
    },
}

WB_ROOT = "https://api.worldbank.org/v2"
REQUEST_TIMEOUT = 25
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")

def wb_source_url(country_code: str, indicator_code: str) -> str:
    return f"https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_code}?format=json"

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_world_bank(country_code: str, indicator_code: str, start_year: int, end_year: int) -> tuple[pd.DataFrame, str | None, str]:
    """Return source observations; missing years are not filled or fabricated."""
    url = wb_source_url(country_code, indicator_code)
    params = {"format": "json", "date": f"{start_year}:{end_year}", "per_page": 2000}
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return pd.DataFrame(columns=["year", "value"]), "The API returned an unexpected or empty response.", url
        records = payload[1]
        if records is None:
            return pd.DataFrame(columns=["year", "value"]), "The API returned no observations for this request.", url
        rows = []
        for item in records:
            yr = item.get("date")
            val = item.get("value")
            if yr is None:
                continue
            try:
                year_int = int(yr)
            except (TypeError, ValueError):
                continue
            if val is not None:
                try:
                    rows.append({"year": year_int, "value": float(val)})
                except (TypeError, ValueError):
                    continue
        df = pd.DataFrame(rows, columns=["year", "value"])
        if df.empty:
            return df, "No non-null numeric observations were returned for this period.", url
        df = df.sort_values("year").drop_duplicates("year", keep="last").reset_index(drop=True)
        return df, None, url
    except requests.Timeout:
        return pd.DataFrame(columns=["year", "value"]), f"World Bank request timed out after {REQUEST_TIMEOUT} seconds.", url
    except requests.RequestException as exc:
        return pd.DataFrame(columns=["year", "value"]), f"Network/API error: {exc}", url
    except (ValueError, TypeError) as exc:
        return pd.DataFrame(columns=["year", "value"]), f"Could not read the API response: {exc}", url

def validate_working_data(df: pd.DataFrame, constraint: str) -> tuple[pd.DataFrame, list[str]]:
    errors = []
    if not {"year", "value"}.issubset(df.columns):
        return pd.DataFrame(columns=["year", "value"]), ["The editable table must contain year and value columns."]
    clean = df[["year", "value"]].copy()
    numeric_year = pd.to_numeric(clean["year"], errors="coerce")
    numeric_value = pd.to_numeric(clean["value"], errors="coerce")
    if numeric_year.isna().any():
        errors.append("Every year must be a whole-number year.")
    else:
        if ((numeric_year % 1) != 0).any():
            errors.append("Years must be integers; decimal years are not allowed.")
        if ((numeric_year < 1900) | (numeric_year > 2100)).any():
            errors.append("Years must be between 1900 and 2100.")
        if numeric_year.duplicated().any():
            errors.append("Duplicate years are not allowed.")
    if numeric_value.isna().any():
        errors.append("Every value must be numeric; blank cells are not valid model observations.")
    if np.isinf(numeric_value.dropna()).any():
        errors.append("Infinite values are not allowed.")
    if constraint in ("positive", "nonnegative") and (numeric_value.dropna() < 0).any():
        errors.append("This indicator cannot have negative values.")
    if constraint == "percent" and ((numeric_value.dropna() < 0) | (numeric_value.dropna() > 100)).any():
        errors.append("Unemployment percentage values must be between 0 and 100.")
    if errors:
        return clean, errors
    clean["year"] = numeric_year.astype(int)
    clean["value"] = numeric_value.astype(float)
    return clean.sort_values("year").reset_index(drop=True), []

def fit_polynomial(df: pd.DataFrame, degree: int) -> tuple[Polynomial, int, np.ndarray, np.ndarray]:
    if len(df) < degree + 1 or df["year"].nunique() < degree + 1:
        raise ValueError(f"Degree {degree} requires at least {degree + 1} distinct valid observations.")
    base_year = int(df["year"].min())
    t = df["year"].to_numpy(dtype=float) - base_year
    y = df["value"].to_numpy(dtype=float)
    # Polynomial.fit scales internally; convert() returns coefficients in ordinary powers of t.
    model = Polynomial.fit(t, y, degree).convert()
    fitted = model(t)
    return model, base_year, fitted, y - fitted

def equation_text(model: Polynomial, base_year: int, degree: int, unit: str) -> str:
    parts = []
    for power, coef in enumerate(model.coef):
        if abs(coef) < 1e-14:
            continue
        if power == 0:
            parts.append(f"{coef:.10g}")
        else:
            parts.append(f"({coef:.10g})·t^{power}")
    rhs = " + ".join(parts).replace("+ (-", "- (")
    return f"y = {rhs or '0'}; t = year − {base_year}. Units: {unit}. Degree {degree}."

def metrics(y: np.ndarray, fitted: np.ndarray) -> dict[str, float]:
    residual = y - fitted
    ss_res = float(np.sum(residual ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"r_squared": r2,
            "mae": float(mean_absolute_error(y, fitted)),
            "rmse": float(np.sqrt(mean_squared_error(y, fitted)))}

def chronological_holdout(df: pd.DataFrame, degree: int) -> dict[str, Any] | None:
    # Reserve the latest 20%, with at least one test row and d+1 training rows.
    n = len(df)
    test_n = max(1, int(math.ceil(n * 0.2)))
    if n - test_n < degree + 1:
        return None
    train, test = df.iloc[:-test_n], df.iloc[-test_n:]
    base = int(train["year"].min())
    t_train = train["year"].to_numpy(float) - base
    model = Polynomial.fit(t_train, train["value"].to_numpy(float), degree).convert()
    prediction = model(test["year"].to_numpy(float) - base)
    actual = test["value"].to_numpy(float)
    return {"n": len(test), "mae": float(np.mean(np.abs(actual-prediction))),
            "rmse": float(np.sqrt(np.mean((actual-prediction)**2))),
            "start": int(test["year"].min()), "end": int(test["year"].max())}

def prediction_is_implausible(value: float, indicator_name: str) -> bool:
    if not np.isfinite(value):
        return True
    if indicator_name == "Life expectancy at birth":
        return value < 0 or value > 120
    if indicator_name == "Unemployment, national estimate":
        return value < 0 or value > 100
    if indicator_name == "Crude birth rate":
        return value < 0 or value > 100
    if indicator_name == "Intentional homicide rate":
        return value < 0 or value > 200
    if indicator_name in ("GDP per capita", "Total reserves including gold", "Central government debt"):
        return value < 0
    return abs(value) > 1e15

def derivative_analysis(model: Polynomial, base_year: int, low: int, high: int) -> dict[str, Any]:
    first, second = model.deriv(1), model.deriv(2)
    # Derivatives are with respect to t, and dt/dyear = 1.
    candidates = [float(low - base_year), float(high - base_year)]
    roots = first.roots()
    critical = sorted(float(r.real) for r in roots if abs(r.imag) < 1e-7 and low-base_year <= r.real <= high-base_year)
    extrema = []
    for x in critical:
        eps = max(1e-4, min(0.1, (high-low)*1e-4))
        left, right = first(x-eps), first(x+eps)
        kind = "local maximum" if left > 0 and right < 0 else "local minimum" if left < 0 and right > 0 else "stationary / unclassified"
        extrema.append((x+base_year, float(model(x)), kind))
    endpoints = [(low, float(model(low-base_year)), "left endpoint"),
                 (high, float(model(high-base_year)), "right endpoint")]
    all_values = endpoints + [(round(y), v, k) for y, v, k in extrema]
    global_min = min(all_values, key=lambda z:z[1])
    global_max = max(all_values, key=lambda z:z[1])
    inflections = []
    for r in second.roots():
        if abs(r.imag) < 1e-7 and low-base_year <= r.real <= high-base_year:
            x = float(r.real)
            eps = max(1e-4, min(0.1, (high-low)*1e-4))
            if second(x-eps) * second(x+eps) < 0:
                inflections.append((x+base_year, float(model(x))))
    return {"first": first, "second": second, "critical": extrema,
            "minimum": global_min, "maximum": global_max, "inflections": inflections}

def make_chart(df: pd.DataFrame, model: Polynomial, base_year: int, degree: int,
               increment: int, horizon: int, single_year: int | None,
               single_value: float | None, batch: pd.DataFrame | None,
               comparison: pd.DataFrame | None, comparison_name: str | None,
               indicator_name: str, unit: str) -> BytesIO:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    years = df["year"].to_numpy(int)
    vals = df["value"].to_numpy(float)
    low, high = int(years.min()), int(years.max())
    end = min(2100, high + horizon)
    curve_years = np.linspace(low, max(high, end), max(300, (max(high,end)-low)*4))
    curve_values = model(curve_years-base_year)
    ax.scatter(years, vals, label="Observed source / edited data", color="#1769aa", s=35, zorder=4)
    ax.plot(curve_years[curve_years <= high], curve_values[curve_years <= high],
            label="Polynomial fit (historical interval)", color="#e07a1f", linewidth=2)
    if end > high:
        mask = curve_years >= high
        ax.plot(curve_years[mask], curve_values[mask], "--", label="Extrapolated segment", color="#b23a48", linewidth=2)
    sample_years = np.arange(low, high+1, increment)
    ax.scatter(sample_years, model(sample_years-base_year), marker="x", color="#333333",
               label=f"Model samples every {increment} year(s)", zorder=3)
    ax.axvline(high, color="gray", linestyle=":", label="Historical boundary")
    if single_year is not None and single_value is not None:
        ax.scatter([single_year], [single_value], marker="*", s=150, color="#7a3db8", label="Single-year estimate", zorder=5)
    if batch is not None and not batch.empty:
        ax.scatter(batch["year"], batch["estimate"], marker="D", s=42, color="#16856b", label="Batch estimates", zorder=5)
    if comparison is not None and not comparison.empty and comparison_name:
        ax.plot(comparison["year"], comparison["value"], linestyle="-.", linewidth=1.5,
                label=f"{comparison_name} (same indicator)")
    ax.set_title(f"{indicator_name} — polynomial degree {degree}")
    ax.set_xlabel("Year")
    ax.set_ylabel(unit)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    out = BytesIO()
    fig.savefig(out, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    out.seek(0)
    return out

def make_excel(summary: dict, data: pd.DataFrame, results: pd.DataFrame) -> bytes:
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
        data.to_excel(writer, sheet_name="Working Data", index=False)
        results.to_excel(writer, sheet_name="Calculated Years", index=False)
        for sheet in writer.sheets.values():
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, 20, 20)
    return out.getvalue()

def make_pdf(summary: dict, data: pd.DataFrame, results: pd.DataFrame, chart_bytes: BytesIO,
             findings: list[str]) -> bytes:
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(letter), rightMargin=0.45*inch,
                            leftMargin=0.45*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
    story = [Paragraph(APP_TITLE, styles["Title"]),
             Paragraph(f"Report generated: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}", styles["Small"]),
             Spacer(1, 8)]
    meta = [[str(k).replace("_"," ").title(), str(v)] for k,v in summary.items()]
    table = Table(meta, colWidths=[1.65*inch, 8.0*inch])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),colors.lightgrey),
                               ("GRID",(0,0),(-1,-1),0.35,colors.grey),
                               ("VALIGN",(0,0),(-1,-1),"TOP"),
                               ("FONTSIZE",(0,0),(-1,-1),8)]))
    story += [table, Spacer(1, 8), Paragraph("Model chart", styles["Heading2"])]
    chart_bytes.seek(0)
    story += [Image(chart_bytes, width=8.7*inch, height=4.75*inch), Paragraph("Findings and limitations", styles["Heading2"])]
    story += [Paragraph("• " + x, styles["Small"]) for x in findings]
    story += [Spacer(1, 6), Paragraph("Working data preview (first 30 rows)", styles["Heading2"])]
    preview = [["Year","Value"]] + [[str(int(r.year)), f"{r.value:.8g}"] for r in data.head(30).itertuples()]
    dt = Table(preview, repeatRows=1, colWidths=[1.0*inch, 1.5*inch])
    dt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),7)]))
    story.append(dt)
    if results is not None and not results.empty:
        story += [Spacer(1,8), Paragraph("Calculated-year results", styles["Heading2"])]
        rows = [["Year","Estimate","Classification"]] + [[str(int(r.year)), f"{r.estimate:.8g}", str(r.classification)] for r in results.itertuples()]
        rt = Table(rows, repeatRows=1, colWidths=[1*inch,1.5*inch,2.5*inch])
        rt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),7)]))
        story.append(rt)
    doc.build(story)
    return out.getvalue()

def parse_batch(mode: str, start: int, stop: int, step: int, custom: str) -> tuple[list[int], list[str]]:
    errors = []
    if mode == "Year range":
        if start > stop:
            return [], ["Range start must be less than or equal to range end."]
        years = list(range(start, stop+1, step))
    else:
        tokens = [x.strip() for x in custom.split(",") if x.strip()]
        years = []
        for token in tokens:
            if not re.fullmatch(r"\d{4}", token):
                errors.append(f"'{token}' is not a valid four-digit year.")
            else:
                y = int(token)
                if not 1950 <= y <= 2100:
                    errors.append(f"{y} is outside the allowed 1950–2100 range.")
                else:
                    years.append(y)
        if len(set(years)) != len(years):
            errors.append("Custom years contain duplicates.")
    if any(y < 1950 or y > 2100 for y in years):
        errors.append("Requested years must be between 1950 and 2100.")
    return sorted(set(years)), errors

# ------------------------------ Interface ------------------------------
st.title("📊 " + APP_TITLE)
st.caption("HISPANIC HERITAGE DATA LAB | World Bank historical indicators and polynomial modeling")
st.info("Start by replacing the research-question and pathway choices in the sidebar. Brazil is included as a Latin American comparison country; it is not a Spanish-speaking country and is not part of Hispanic heritage in the narrow cultural/linguistic sense.")

with st.sidebar:
    st.header("Research setup")
    research_question = st.text_area("Research question", "How has life expectancy changed over time in selected Latin American countries?", height=85)
    country_label = st.selectbox("Featured country", list(COUNTRIES))
    indicator_name = st.selectbox("Indicator", list(INDICATORS))
    pathway = st.selectbox("Mathematics pathway", ["Honors Algebra 2", "Precalculus", "Calculus"])
    degree = st.slider("Polynomial degree", 3, 8, 3)
    increment = st.slider("Graph sample increment (years)", 1, 10, 5)
    horizon = st.slider("Forward display horizon (years)", 0, 50, 10)
    comparison_label = st.selectbox("Comparison country", ["None"] + [x for x in COUNTRIES if x != country_label])
    printer_mode = st.checkbox("Printer-friendly view", value=False)

current_year = date.today().year
start_year, end_year = current_year - 70, current_year - 1
country_code = COUNTRIES[country_label]
indicator = INDICATORS[indicator_name]
source_df, fetch_error, source_url = fetch_world_bank(country_code, indicator["code"], start_year, end_year)
retrieved_on = date.today().isoformat()

if "active_signature" not in st.session_state:
    st.session_state.active_signature = None
signature = (country_code, indicator["code"], degree)
if st.session_state.active_signature != signature:
    st.session_state.active_signature = signature
    st.session_state.single_result = None
    st.session_state.batch_result = pd.DataFrame()
    st.session_state.single_input = 2020

if fetch_error:
    st.error(fetch_error)
    st.caption(f"Source endpoint: {source_url}")
    st.warning("No substitute or random values are used. Choose another country/indicator or retry later.")
    st.stop()
if source_df.empty:
    st.warning("The source returned no usable observations for the requested period.")
    st.stop()

if "source_data" not in st.session_state or st.session_state.get("source_key") != (country_code, indicator["code"], start_year, end_year):
    st.session_state.source_data = source_df.copy()
    st.session_state.working_data = source_df.copy()
    st.session_state.source_key = (country_code, indicator["code"], start_year, end_year)
    st.session_state.data_revision = 0
    st.session_state.single_result = None
    st.session_state.batch_result = pd.DataFrame()

original = st.session_state.source_data.copy()
st.subheader("1. Source and indicator")
coverage = f"{int(original.year.min())}–{int(original.year.max())}" if not original.empty else "none"
c1,c2,c3,c4 = st.columns(4)
c1.metric("Non-null observations", f"{len(original)}")
c2.metric("Actual year coverage", coverage)
c3.metric("Requested year window", f"{start_year}–{end_year}")
c4.metric("Retrieved", retrieved_on)
st.markdown(f"**Definition:** {indicator['definition']}")
st.markdown(f"**Unit:** {indicator['unit']}  \n**World Bank indicator:** `{indicator['code']}`  \n**Source:** [{source_url}]({source_url})")
st.caption(indicator["caveat"])
st.caption("The requested window is current year − 70 through current year − 1. Actual coverage and count above reflect only non-null numeric observations returned by the API.")

st.subheader("2. Review and edit working data")
st.write("The source copy stays unchanged. Edit the table below to explore a scenario; edited values are labeled as user-modified and are not represented as official World Bank observations.")
if st.button("Reset to source", key="reset_source"):
    st.session_state.working_data = original.copy()
    st.session_state.data_revision += 1
    st.session_state.single_result = None
    st.session_state.batch_result = pd.DataFrame()
    st.rerun()
edited = st.data_editor(st.session_state.working_data, num_rows="dynamic", use_container_width=True,
                        key=f"editor_{st.session_state.data_revision}")
if not edited.equals(st.session_state.working_data):
    st.session_state.working_data = edited.copy()
    st.session_state.data_revision += 1
    st.session_state.single_result = None
    st.session_state.batch_result = pd.DataFrame()
    st.rerun()
working, validation_errors = validate_working_data(st.session_state.working_data, indicator["constraint"])
is_modified = not working.equals(original.reset_index(drop=True))
if is_modified:
    st.warning("USER-MODIFIED SCENARIO — results use the edited working table, not only the source observations.")
else:
    st.success("Working data currently matches the retrieved source observations.")
if validation_errors:
    for error in validation_errors: st.error(error)
    st.stop()
if len(working) < degree+1:
    st.error(f"Degree {degree} needs at least {degree+1} distinct valid years; the working table has {len(working)}.")
    st.stop()

# Model and diagnostics
model, base_year, fitted, residuals = fit_polynomial(working, degree)
y = working["value"].to_numpy(float)
fit_metrics = metrics(y, fitted)
low, high = int(working.year.min()), int(working.year.max())
eq = equation_text(model, base_year, degree, indicator["unit"])
holdout = chronological_holdout(working, degree)
model_signature = (country_code, indicator["code"], degree, st.session_state.data_revision, tuple(working.year), tuple(np.round(working.value, 12)))

st.subheader("3. Polynomial model and fit")
st.code(eq)
m1,m2,m3,m4 = st.columns(4)
m1.metric("R² (in-sample)", f"{fit_metrics['r_squared']:.6f}" if np.isfinite(fit_metrics["r_squared"]) else "undefined")
m2.metric("MAE (in-sample)", f"{fit_metrics['mae']:.6g} {indicator['unit']}")
m3.metric("RMSE (in-sample)", f"{fit_metrics['rmse']:.6g} {indicator['unit']}")
m4.metric("Observations", str(len(working)))
st.caption(f"Base year: {base_year} | Degree: {degree} | Historical range: {low}–{high} | Mean: {np.mean(y):.8g} {indicator['unit']}. R², MAE, and RMSE describe fit to the same observations used to estimate the polynomial; they are in-sample metrics.")
if holdout:
    st.write(f"**Chronological holdout (separate check):** trained on {low}–{holdout['start']-1}; tested on {holdout['start']}–{holdout['end']} ({holdout['n']} latest observations). Holdout MAE = {holdout['mae']:.6g}; RMSE = {holdout['rmse']:.6g}.")
else:
    st.caption("Chronological holdout not shown: there are not enough observations to retain at least degree + 1 training points and a test observation.")
residual_table = working[["year"]].copy()
residual_table["observed"] = y
residual_table["fitted"] = fitted
residual_table["residual (observed − fitted)"] = residuals
with st.expander("Inspect residuals"):
    st.dataframe(residual_table, use_container_width=True)

st.subheader("4. Calculate estimates")
st.caption("Polynomial estimates are mathematical model outputs, not official forecasts. Extrapolation can become unstable, especially at high degrees or far outside the observed years.")
single_year = st.number_input("Single year (1950–2100)", min_value=1950, max_value=2100,
                              value=int(st.session_state.get("single_input", min(max(2020,low),2100))), step=1)
if st.button("Calculate Value"):
    estimate = float(model(single_year-base_year))
    st.session_state.single_result = {"signature": model_signature, "year": int(single_year), "estimate": estimate}
    st.session_state.single_input = int(single_year)
    st.rerun()
single = st.session_state.single_result
single_plot_year, single_plot_value = None, None
if single and single.get("signature") == model_signature:
    yr, est = single["year"], single["estimate"]
    classification = "within fitted historical range" if low <= yr <= high else "outside fitted historical range (extrapolation)"
    actual_match = working.loc[working.year == yr, "value"]
    st.metric(f"Estimate for {yr}", f"{est:.8g} {indicator['unit']}")
    st.write(f"**Classification:** {classification}. **Actual fitted range:** {low}–{high}.")
    if not actual_match.empty:
        st.write(f"At this observed year, the source/working-table actual is **{float(actual_match.iloc[0]):.8g} {indicator['unit']}**; the model estimate is a separate fitted value.")
    else:
        st.write("No actual observation exists in the working table for this year.")
    if prediction_is_implausible(est, indicator_name):
        st.error("Warning: this estimate is outside a broad plausibility check for this indicator. It is not clipped; inspect the model and avoid treating it as a credible forecast.")
    single_plot_year, single_plot_value = yr, est
else:
    if single:
        st.info("The saved single-year result was cleared because its model/data settings changed.")

with st.expander("Batch estimates", expanded=True):
    batch_mode = st.radio("Batch input type", ["Year range", "Custom years"], horizontal=True)
    bcol1,bcol2,bcol3 = st.columns(3)
    range_start = bcol1.number_input("Range start", 1950, 2100, max(1950,low), 1)
    range_end = bcol2.number_input("Range end", 1950, 2100, min(2100,high+10), 1)
    range_step = bcol3.number_input("Range step", 1, 10, 1, 1)
    custom_years = st.text_input("Comma-separated custom years", "2000, 2010, 2020")
    if st.button("Calculate batch"):
        years, parse_errors = parse_batch(batch_mode, int(range_start), int(range_end), int(range_step), custom_years)
        if parse_errors:
            for err in parse_errors: st.error(err)
            st.session_state.batch_result = pd.DataFrame()
        elif not years:
            st.error("Enter at least one valid year.")
            st.session_state.batch_result = pd.DataFrame()
        else:
            results = []
            for yr in years:
                est = float(model(yr-base_year))
                cls = "within fitted range" if low <= yr <= high else "outside fitted range"
                actual = working.loc[working.year == yr, "value"]
                results.append({"year":yr, "estimate":est, "unit":indicator["unit"], "classification":cls,
                                "actual_observation":float(actual.iloc[0]) if not actual.empty else np.nan,
                                "implausibility_flag":prediction_is_implausible(est,indicator_name)})
            st.session_state.batch_result = pd.DataFrame(results)
            st.session_state.batch_signature = model_signature
            st.rerun()
batch = st.session_state.batch_result.copy()
if not batch.empty and st.session_state.get("batch_signature") == model_signature:
    st.dataframe(batch, use_container_width=True)
else:
    batch = pd.DataFrame()
    if not st.session_state.batch_result.empty:
        st.info("Batch results were cleared because the model/data settings changed.")

st.subheader("5. Graph and country comparison")
comparison_df, comparison_error, comparison_url = None, None, None
comparison_name = None
if comparison_label != "None":
    comparison_name = comparison_label
    comparison_code = COUNTRIES[comparison_label]
    comparison_df, comparison_error, comparison_url = fetch_world_bank(comparison_code, indicator["code"], start_year, end_year)
    if comparison_error:
        st.warning(f"Comparison data unavailable: {comparison_error}")
        comparison_df = None
    elif comparison_df.empty:
        st.warning("The comparison country has no usable observations in this period.")
        comparison_df = None
    else:
        overlap = sorted(set(working.year) & set(comparison_df.year))
        st.caption(f"{comparison_label} coverage: {comparison_df.year.min()}–{comparison_df.year.max()} ({len(comparison_df)} observations). Shared years with featured country: {len(overlap)}. Lines may have different coverage; missing years are not interpolated.")
        st.caption(f"Comparison source: {comparison_url}")
chart = make_chart(working, model, base_year, degree, increment, horizon, single_plot_year,
                   single_plot_value, batch if not batch.empty else None,
                   comparison_df, comparison_name, indicator_name, indicator["unit"])
if printer_mode:
    st.markdown("### Printer-friendly report")
    st.write(f"**Question:** {research_question}")
    st.write(f"**Country / indicator:** {country_label} / {indicator_name}")
    st.write(f"**Equation:** {eq}")
    st.write(f"**In-sample R²:** {fit_metrics['r_squared']:.6f} | **MAE:** {fit_metrics['mae']:.6g} | **n:** {len(working)}")
    st.image(chart, use_container_width=True)
else:
    st.image(chart.getvalue(), use_container_width=True)
    st.caption(f"Graph sample increment: model markers are placed every {increment} year(s). The smooth curve is plotted separately. Forward display horizon: {horizon} year(s).")

st.subheader("6. Mathematics pathway interpretation")
mean_rate = (float(working.value.iloc[-1])-float(working.value.iloc[0]))/(int(working.year.iloc[-1])-int(working.year.iloc[0])) if len(working)>1 else float("nan")
st.write(f"**Domain of observed data:** discrete observed years {low}–{high}. **Model display domain:** {low}–{min(2100,high+horizon)}. **Observed range:** {working.value.min():.8g} to {working.value.max():.8g} {indicator['unit']}.")
st.write(f"**Average rate of change across the observed endpoints:** {mean_rate:.8g} {indicator['unit']} per year. This summarizes endpoints and does not describe every year.")
st.write(f"**End behavior:** the highest nonzero power term controls the polynomial's mathematical behavior as t approaches positive or negative infinity. That behavior may be far outside any realistic range for the indicator.")
if pathway in ("Precalculus", "Calculus"):
    st.write("**Degree and coefficients:** degree is the highest power of centered time with a nonzero coefficient. Coefficient signs and magnitudes shape curvature and turning behavior; larger degree can fit more bends but can also overfit and extrapolate poorly.")
    changes = np.diff(working.value.to_numpy(float)) / np.diff(working.year.to_numpy(float))
    st.write(f"**Changing average rates:** year-to-year secant slopes range from {np.min(changes):.8g} to {np.max(changes):.8g} {indicator['unit']} per year. A change in these slopes is evidence that the trend is not constant.")
if pathway == "Calculus":
    calc = derivative_analysis(model, base_year, low, high)
    st.write("**First derivative:** instantaneous model rate of change. **Second derivative:** change in that rate (concavity). Derivatives describe the fitted polynomial, not an independently measured causal mechanism.")
    st.write(f"First derivative: `{calc['first']}`")
    st.write(f"Second derivative: `{calc['second']}`")
    st.write("**Critical points in the historical interval:** " + (", ".join(f"{yr:.3f}: {val:.6g} ({kind})" for yr,val,kind in calc["critical"]) if calc["critical"] else "none found."))
    st.write(f"**Interval minimum including endpoints:** year {calc['minimum'][0]:.3f}, {calc['minimum'][1]:.8g} ({calc['minimum'][2]}).")
    st.write(f"**Interval maximum including endpoints:** year {calc['maximum'][0]:.3f}, {calc['maximum'][1]:.8g} ({calc['maximum'][2]}).")
    st.write("**Verified inflection points:** " + (", ".join(f"year {yr:.3f}, value {val:.6g}" for yr,val in calc["inflections"]) if calc["inflections"] else "none found in the historical interval."))
    tangent_year = st.number_input("Tangent-line year", min_value=1950, max_value=2100, value=min(max((low+high)//2,1950),2100), key="tangent_year")
    tangent_t = tangent_year-base_year
    tangent_slope = float(calc["first"](tangent_t))
    tangent_value = float(model(tangent_t))
    st.write(f"Tangent line at {tangent_year}: y = {tangent_value:.8g} + ({tangent_slope:.8g})(year − {tangent_year}).")
    sec_col1, sec_col2 = st.columns(2)
    sec_a = sec_col1.number_input("Secant start year", 1950, 2100, low, key="sec_a")
    sec_b = sec_col2.number_input("Secant end year", 1950, 2100, high, key="sec_b")
    if sec_a != sec_b:
        sec_slope = (float(model(sec_b-base_year))-float(model(sec_a-base_year)))/(sec_b-sec_a)
        st.write(f"Secant slope from {sec_a} to {sec_b}: {sec_slope:.8g} {indicator['unit']} per year.")
    else:
        st.warning("Choose two different years to calculate a secant line.")
else:
    st.write("**Interpretation focus:** describe the plotted direction, bends, and average rate of change. Do not claim the polynomial proves why the indicator changed.")

st.subheader("7. Findings, uncertainty, and limitations")
findings = [
    f"The selected World Bank indicator is {indicator_name} ({indicator['code']}) for {country_label}.",
    f"The working data contain {len(working)} observations from {low} through {high}; actual coverage may be shorter than the requested 70-year window.",
    f"A degree-{degree} polynomial was fit to centered time t = year − {base_year}. In-sample MAE is {fit_metrics['mae']:.6g} {indicator['unit']}.",
    f"Residuals and MAE describe historical fit, not a validated 95% prediction interval. Extrapolation is uncertain and can become implausible.",
    indicator["caveat"],
    "The polynomial is descriptive, does not establish causation, and does not incorporate policy, demographic, economic, or other explanatory variables."
]
for item in findings: st.write("• " + item)
st.warning("No 95% prediction interval is displayed. Residual size/MAE is a baseline description of in-sample error, not a calibrated uncertainty interval. Predictions outside the observed range are extrapolations.")

st.subheader("8. Export current results")
summary = {
    "research_question": research_question, "country": country_label, "country_code": country_code,
    "indicator": indicator_name, "indicator_code": indicator["code"], "unit": indicator["unit"],
    "definition": indicator["definition"], "mathematics_pathway": pathway, "degree": degree,
    "base_year": base_year, "historical_start": low, "historical_end": high,
    "observation_count": len(working), "retrieval_date": retrieved_on,
    "source_url": source_url, "data_status": "USER-MODIFIED SCENARIO" if is_modified else "source data unchanged",
    "equation": eq, "in_sample_r_squared": fit_metrics["r_squared"],
    "in_sample_mae": fit_metrics["mae"], "in_sample_rmse": fit_metrics["rmse"],
    "holdout_mae": holdout["mae"] if holdout else None,
}
results_export = batch.copy() if not batch.empty else pd.DataFrame(columns=["year","estimate","unit","classification","actual_observation","implausibility_flag"])
if single and single.get("signature") == model_signature:
    single_row = pd.DataFrame([{"year":single["year"],"estimate":single["estimate"],"unit":indicator["unit"],
                                "classification":"single-year result","actual_observation":np.nan,
                                "implausibility_flag":prediction_is_implausible(single["estimate"],indicator_name)}])
    results_export = pd.concat([single_row, results_export], ignore_index=True)
csv_export = working.copy()
csv_export["fitted_value"] = fitted
csv_export["residual_observed_minus_fitted"] = residuals
csv_export["country"] = country_label
csv_export["indicator"] = indicator_name
csv_export["indicator_code"] = indicator["code"]
csv_export["degree"] = degree
csv_export["data_status"] = "USER-MODIFIED SCENARIO" if is_modified else "source data unchanged"
csv_bytes = csv_export.to_csv(index=False).encode("utf-8")
excel_bytes = make_excel(summary, working, results_export)
pdf_bytes = make_pdf(summary, working, results_export, chart, findings)
d1,d2,d3 = st.columns(3)
d1.download_button("Download working data CSV", csv_bytes, file_name="hispanic_heritage_working_data.csv", mime="text/csv")
d2.download_button("Download Excel workbook", excel_bytes, file_name="hispanic_heritage_analysis.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
d3.download_button("Download PDF report", pdf_bytes, file_name="hispanic_heritage_report.pdf", mime="application/pdf")

st.divider()
st.caption("Data source: World Bank Open Data API. This classroom explorer is an analytical aid, not an official forecast or policy evaluation.")
