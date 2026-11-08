# Equipment Lending System

A Python application for managing equipment and date-based loans. It includes a browser-based web application with HTML forms, a resource-oriented REST API, a command-line interface, SQLite persistence, automated tests, and Docker Compose support.

## Features

- Browser forms for equipment and loan workflows.
- REST API with JSON requests and responses.
- Automatically generated OpenAPI specification and Swagger UI.
- CLI for the original assignment commands.
- SQLite persistence and validation of loan date ranges.
- Prevention of overlapping active loans.
- Automated API and web-form tests.
- Docker image and persistent Docker Compose volume.

## 1. Requirements

For local development:

- Python 3.10 or newer
- pip

For container deployment:

- Docker Desktop with Docker Compose

## 2. Install locally

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## 3. Start the web application

From the project root, with the virtual environment activated:

```bash
uvicorn lending:app --reload
```

Open the web application:

- **Web application:** http://127.0.0.1:8000/
- **Equipment management:** http://127.0.0.1:8000/ui/equipment
- **Loan management:** http://127.0.0.1:8000/ui/loans
- **Availability search:** http://127.0.0.1:8000/ui/availability
- **Swagger UI:** http://127.0.0.1:8000/docs
- **OpenAPI JSON:** http://127.0.0.1:8000/openapi.json

Stop the local development server with `Ctrl+C`.

## 4. Web application workflows

The browser interface provides forms for the existing assignment workflows:

### Equipment

- View all equipment.
- Add equipment with a name and description.
- Edit equipment details.
- Remove equipment when it has no active loans.

### Loans

- View active and cancelled loans.
- Create a loan by selecting equipment and entering start/end dates.
- Change the dates of an active loan.
- Cancel an active loan.

### Availability

- Search equipment by start and end dates.
- Results exclude equipment with an overlapping active loan.

The web forms call the same application functions as the CLI and REST API, so the business rules are shared.

## 5. Command-line interface

The CLI remains available.

Show help:

```bash
python lending.py --help
python lending.py equipment --help
python lending.py loan --help
```

Equipment examples:

```bash
python lending.py equipment list
python lending.py equipment add --name "Laptop" --description "Dell laptop"
python lending.py equipment update 1 --name "HP Laptop"
python lending.py equipment remove 2
python lending.py equipment search --from 2026-11-01 --to 2026-11-05
```

Loan examples:

```bash
python lending.py loan list
python lending.py loan create --equipment 1 --from 2026-11-01 --to 2026-11-05
python lending.py loan change 1 --to 2026-11-06
python lending.py loan cancel 1
```

Dates must use `YYYY-MM-DD`. Loan dates are inclusive: if one loan ends on November 5, another loan for the same item cannot start on November 5.

## 6. REST API

The JSON API uses resource-oriented URLs.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/equipment` | List equipment |
| POST | `/equipment` | Add equipment |
| PATCH | `/equipment/{equipment_id}` | Update equipment fields |
| DELETE | `/equipment/{equipment_id}` | Remove equipment without active loans |
| GET | `/loans` | List loans |
| POST | `/loans` | Create a loan |
| PATCH | `/loans/{loan_id}` | Change loan dates |
| POST | `/loans/{loan_id}/cancel` | Cancel a loan |
| GET | `/equipment/search?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | Search availability |

### Example JSON requests

Create equipment:

```json
{
  "name": "Laptop",
  "description": "Dell laptop"
}
```

Create a loan:

```json
{
  "equipment_id": 1,
  "start_date": "2026-11-01",
  "end_date": "2026-11-05"
}
```

Change a loan:

```json
{
  "end_date": "2026-11-06"
}
```

### HTTP status codes

- `200 OK`: successful retrieval or update.
- `201 Created`: equipment or loan created.
- `204 No Content`: equipment successfully deleted.
- `400 Bad Request`: invalid input or invalid date range.
- `404 Not Found`: equipment or loan does not exist.
- `409 Conflict`: overlapping loan or operation blocked by an active loan.
- `422 Unprocessable Entity`: request body or parameter validation failed.

The interactive documentation is available at `/docs`. FastAPI exposes the OpenAPI JSON document at `/openapi.json`.

To save a copy of the OpenAPI specification after starting the application:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/openapi.json -OutFile openapi.json
```

## 7. Business rules

1. Equipment names cannot be empty.
2. Dates must be valid ISO dates (`YYYY-MM-DD`).
3. The end date cannot be earlier than the start date.
4. An equipment item cannot have two active loans with overlapping dates.
5. Cancelled loans remain in the database for history and do not block availability.
6. Equipment with active loans cannot be deleted.
7. Availability search excludes equipment whose active loan overlaps the requested date range.

## 8. Automated tests

Install development dependencies (already included when using `requirements-dev.txt`):

```bash
python -m pip install -r requirements-dev.txt
```

Run all tests:

```bash
python -m pytest -q
```

Tests use temporary SQLite databases so they do not modify the normal development database.

## 9. Run with Docker Compose

Make sure Docker Desktop is running. From the project root, build and start the application:

```bash
docker compose up --build -d
```

Check the container:

```bash
docker compose ps
```

Open the application:

- **Web application:** http://localhost:8000/
- **Swagger UI:** http://localhost:8000/docs

View logs:

```bash
docker compose logs -f web
```

Stop and remove the application container:

```bash
docker compose down
```

The named volume `equipment-lending-data` is preserved by `docker compose down`, so the SQLite database remains available when the application is started again.

Start it again:

```bash
docker compose up -d
```

To remove the database volume as well (this permanently deletes the stored application data):

```bash
docker compose down -v
```

Do not use `-v` when you want to preserve loan and equipment records.


## 10. Database

The SQLite database is created automatically. By default, local development stores it as `lending.db` in the current working directory.

Set `LENDING_DB` to use another database path. Docker Compose sets it to `/data/lending.db` and mounts the named `equipment-lending-data` volume at `/data`.

Local SQLite database files, journal files, Python virtual environments, and test caches are excluded through `.gitignore` and `.dockerignore`.
