# sistat

A small Python client for [SiStat](https://pxweb.stat.si/SiStat), the statistical database of the
Statistical Office of the Republic of Slovenia (SURS). Use it to search tables, inspect their
variables, and download data as a pandas DataFrame.

SiStat runs [PxWeb](https://www.scb.se/en/services/statistical-programs-for-px-files/px-web/),
whose v1 API is documented in
[SURS's API help (PDF)](https://www.stat.si/StatWeb/File/DocSysFile/10722/px_web_api_helpEN.pdf).

## Install

```bash
pip install "sistat[pandas] @ git+https://github.com/jprevc/sistat"
```

Without the `pandas` extra, `get_records()` returns plain dicts.

## Usage

```python
import sistat

c = sistat.Client(lang="en")          # or "sl"

c.search("air temperatures")          # case- and accent-insensitive, searched locally
# [TableInfo(id='0156101S.px', text='Average annual and monthly air temperatures [°C] by ...', ...)]

meta = c.metadata("0156101S")         # the ".px" suffix is optional
for v in meta.variables:
    print(v.code, "|", v.text, "|", v.value_texts[:3])
# METEOROLOŠKA POSTAJA | METEOROLOGICAL STATION | ('SLOVENIA', 'Bilje', 'Bovec')
# OBDOBJE, LETO | PERIOD, YEAR | ('1981-1990', '1991-2000', '2001-2010')
# MERITVE | MEASURE | ('Average temperature - ANNUAL', 'January', 'February')

df = c.get(
    "0156101S",
    {
        "METEOROLOGICAL STATION": ["Ljubljana, Bežigrad", "Maribor, Tabor"],
        "PERIOD, YEAR": "201*",
    },
)
#   METEOROLOGICAL STATION  PERIOD, YEAR                       MEASURE  value
# 0    Ljubljana, Bežigrad          2010  Average temperature - ANNUAL   10.7
# ...
```

### Selections

Keys are variables, given as their code (often Slovenian, even in the English API) or their
label, case-insensitively. Values can be:

| Selection                         | Meaning                                    |
|-----------------------------------|--------------------------------------------|
| `"Ljubljana, Bežigrad"` or `"10"` | one value, by label or code                |
| `["10", "Maribor, Tabor"]`        | several values                             |
| `"2020*"`, `"*"`                  | glob pattern over codes and labels         |
| `"top:5"`                         | the first 5 values in the table's order    |

The library sends every variable you leave out with all its values selected. PxWeb would
otherwise drop it from the result without telling you.

Pass `codes=True` to also get a `<variable>_code` column with the raw value codes. Queries that
exceed the server's cell limit are split into several requests and merged. Requests are kept
under the server's rate limit automatically.

## Layout

- `sistat.pxweb`: a generic PxWeb **v1** client (HTTP, rate limiting, query building, json-stat2
  parsing). It never imports from the SiStat layer, so it could be split into its own package.
- `sistat.Client`: SiStat specifics such as the base URL, table-id normalisation, cached table
  search and lookup by label.

## Development

```bash
uv sync
uv run pytest            # offline tests against recorded fixtures
uv run pytest -m live    # hits the real API
uv run ruff check .
```

Data © SURS, see their [terms of use](https://www.stat.si/StatWeb/en/LegalNotice).
