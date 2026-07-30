# Refactored structure

The application keeps `main/views.py` as a compatibility facade. Existing URL imports therefore continue to work.

## Split view packages

- `main/view_modules/sales/` separates POS, creation, listing, exports, management, and pending sales.
- `main/view_modules/finance/` separates banking, salesman payments, expenses, and suppliers.
- `main/view_modules/customers/` separates management, exports, and reports.
- `main/view_modules/salesmen/` separates management, reports, and POS.
- `main/view_modules/catalogue/` separates product management, details, reports, and APIs.

Each package re-exports the original function names from `__init__.py`, so the existing facade and URL configuration remain compatible.

## Templates

Safe inline CSS and JavaScript blocks that do not contain Django template expressions were extracted from oversized templates into `static/css/pages/` and `static/js/pages/`. Template-dependent scripts remain inline.

## Archive

Obsolete code, duplicate templates, maintenance scripts, and logs are retained under `archive/` and are no longer mixed with active application modules.
