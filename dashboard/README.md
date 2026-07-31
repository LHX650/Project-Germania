# Project Germania Dashboard

Phase 17A creates the standalone Streamlit presentation foundation for **Project Germania — German Automotive Market Intelligence**. It contains navigation, page shells, shared components, responsive styling, and a read-only database service interface. It does not query the supplied reports or a SQLite database.

## 1. Create and activate a virtual environment

Run these commands from the project root.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

## 2. Install the existing project dependencies

The complete repository documentation identifies `pyproject.toml` as the dependency manifest and documents this command:

```powershell
python -m pip install -e ".[dev]"
```

The supplied Phase 17 handover archive does **not** contain `pyproject.toml` or a requirements file, although the handover refers to one. Do not run the editable-install command in this reduced archive; first restore the matching `pyproject.toml` from the complete project repository.

Streamlit is also not declared in the package metadata included with this handover. Phase 17A does not add or install dependencies. The dashboard can be started only in an environment where the project's approved Streamlit dependency is already available.

## 3. Run the dashboard

From the project root, use the single supported entry point:

```powershell
streamlit run dashboard/app.py
```

## 4. Phase 17A scope

The current foundation provides:

- wide-screen Streamlit configuration;
- enterprise-style responsive visual theme;
- left navigation for all six planned pages;
- project, phase, and data-connection status labels;
- reusable page headers, placeholders, and footer;
- a database service skeleton that can only open an existing SQLite file in read-only mode.

Phase 17A deliberately provides no simulated data, SQL queries, market analysis, Market Monitor logic, database writes, schema changes, migrations, or scraper activity.

## 5. Phase 17B direction

Phase 17B can connect the pages to a verified SQLite file exclusively through `dashboard/services/database.py`. The connection must remain read-only, page modules must not access SQLite directly, and missing database files must continue to fail clearly without being created automatically.
