# ReicheltAutoImport

An InvenTree plugin that imports Reichelt Elektronik parts from a product page
URL, using the [ReicheltAPI](https://github.com/jkreucher/ReicheltAPI) scraper.

## Installation

### InvenTree Plugin Manager

Install the package in the InvenTree environment, then enable **Reichelt
Auto Import** from the plugin settings.

### Command Line

To install manually via the command line, run the following command:

```bash
pip install inventree-reichelt-auto-import
```

### About the ReicheltAPI dependency

[ReicheltAPI](https://github.com/jkreucher/ReicheltAPI) is not published on
PyPI and is licensed under the **GPLv3**, so its source is not vendored into
this (MIT-licensed) repository. Instead, this plugin loads the upstream
`reichelt.py` module at runtime:

- If a `reichelt` module is already importable in your environment (e.g. you
  installed/cloned it yourself and added it to `PYTHONPATH`), it is used
  as-is.
- Otherwise, it is downloaded from the **ReicheltAPI Module Source** plugin
  setting, which defaults to the project's GitHub raw URL. You can point this
  setting at a local file path instead if you prefer to pin/vendor your own
  copy.

## Configuration

Set the following in the plugin settings:

- **Reichelt Supplier** - the supplier `Company` record used for imported
  parts (falls back to any supplier company named "Reichelt").
- **Category Root Path** - InvenTree category prefix parts are filed under
  (default `Electronics/Reichelt`). Reichelt's own breadcrumb categories are
  created below this path automatically.
- **Default Category Path** - fallback category when no breadcrumb is
  available.
- **ReicheltAPI Module Source** - see above.
- **Default Stock Location** - used when a quantity is supplied (also
  overridable per-user).
- **Timeout Seconds** - HTTP timeout for fetching product pages.

## Usage

Paste a Reichelt product page URL as the "code" (via the dashboard widget,
the plugin settings page, or the API endpoint below). Quantity defaults to
`1` if not supplied.

- `POST /api/plugin/reichelt-auto-import/import/`
  ```json
  { "code": "https://www.reichelt.com/de/en/shop/product/...", "quantity": 1 }
  ```

The part is created/updated using the price for a quantity of 1 as its unit
price, all reported quantity price breaks are imported as supplier price
breaks, and all technical parameters reported by Reichelt are imported as
part parameters. Scanning a barcode/QR code whose payload contains a
Reichelt product URL will trigger the same import automatically.

## Frontend development

The UI (dashboard widget + plugin settings panel) lives in `frontend/` and is
built with Vite into `reichelt_auto_import/static/`.

**Unlike most Python-only InvenTree plugins, the built `static/` output here
is committed to git rather than gitignored.** This is intentional: the
InvenTree *production* Docker image has no Node/npm installed (only its
internal `dev`/`builder` build stages do), so a plugin install triggered via
`plugins.txt` (`pip install -e ...` or `pip install git+...`) cannot run a
frontend build step on the server. If the static output isn't already present
in the installed source tree, the plugin's UI panels fail to load with a
"blocked because of a disallowed MIME type" browser error (the static file
simply doesn't exist -> 404).

**After changing anything under `frontend/src`, rebuild and commit the
result:**

```bash
cd frontend
npm install
npm run build
git add ../reichelt_auto_import/static
```

A pre-commit hook (`scripts/build_frontend_static.sh`) automates this: it
rebuilds and stages `reichelt_auto_import/static` automatically whenever
`frontend/` source changes are part of a commit, and fails the commit so you
can review the rebuilt output before committing it for real. Install it with:

```bash
pip install pre-commit
pre-commit install
```

