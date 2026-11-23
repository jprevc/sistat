# sistat

Reading statistical data from SiStat, the PxWeb database of the Statistical Office of Slovenia (SURS).

The PxWeb terms (Table, Variable, Value, Cell, Selection, Folded match, Record, Cell limit, Rate limit) are defined in [pxweb's glossary](https://github.com/jprevc/pxweb/blob/main/GLOSSARY.md). This file only adds what is specific to SiStat.

## Language

**SiStat**:
The statistical database of SURS, served by PxWeb as the database `Data`, in English or Slovenian.
_Avoid_: SURS database, the API

**Table id**:
A Table's id in canonical form, upper case with the `.px` suffix (`0156101S.px`). Users may write it in any case and without the suffix.
_Avoid_: table code, matrix id

**Table search**:
Finding Tables whose id or title contains every word of the user's text, compared by Folded match. It runs locally over the full list of Tables, which is fetched once.
_Avoid_: lookup, query
