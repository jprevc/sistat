# sistat

Reading statistical data from SiStat, the PxWeb database of the Statistical Office of Slovenia (SURS).

## Language

### Data model

**Table**:
A published multidimensional dataset in the database, identified by an id such as `0156101S.px`.
_Avoid_: dataset, matrix

**Variable**:
One axis of a Table, with a code (often Slovenian) and a human-readable label.
_Avoid_: dimension, column, field

**Value**:
One category of a Variable, with a code and a label.
_Avoid_: category, item, level

**Cell**:
One combination of a Value from each Variable of a Table, carrying a single number (possibly missing) and an optional status symbol.
_Avoid_: data point, observation

### Asking for data

**Selection**:
What the user asks for on one Variable: a Value by code or label, several Values, a glob pattern, or the first N Values. A Variable that isn't mentioned is selected in full.
_Avoid_: filter, query

**Record**:
A Cell flattened into one mapping of Variable label to Value label, plus the number.
_Avoid_: row

**Cell limit**:
The most Cells the server will return for one request. Larger requests have to be split.
_Avoid_: max values
