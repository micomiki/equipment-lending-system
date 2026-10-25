# Equipment Lending

A small Python project implementing the Equipment Lending assignment with:
- A command-line interface matching the sample commands.
- A persistent SQLite database (`lending.db`).
- A REST API documented automatically by FastAPI.
- Date validation and prevention of overlapping active loans.

## 1. Requirements

- Python 3.10 or newer
- pip

## 2. Install

Create and activate a virtual environment (recommended).

Windows:
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Try the CLI

```bash
python lending.py --help
python lending.py equipment --help
python lending.py loan --help

python lending.py equipment list
python lending.py equipment add --name "Laptop" --description "Dell Laptop"
python lending.py equipment add --name "Projector" --description "HDMI Projector"
python lending.py equipment update 1 --name "HP Laptop"
python lending.py equipment update 1 --description "HP Laptop, 16 GB RAM"
python lending.py equipment update 1 --name "HP Laptop" --description "16 GB RAM"
python lending.py equipment remove 2
python lending.py equipment search --from 2026-11-01 --to 2026-11-05

python lending.py loan list
python lending.py loan create --equipment 1 --from 2026-11-01 --to 2026-11-05
python lending.py loan change 1 --from 2026-11-02
python lending.py loan change 1 --to 2026-11-06
python lending.py loan change 1 --from 2026-11-02 --to 2026-11-06
python lending.py loan cancel 1

```

Dates must use `YYYY-MM-DD`. 

The database is created automatically as `lending.db` in the current working directory. 

## 4. Start the REST API

```bash
uvicorn lending:app --reload
```

Then visit:
- API documentation: http://127.0.0.1:8000/docs
- API root: http://127.0.0.1:8000/

## 5. API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/equipment` | List equipment |
| POST | `/equipment` | Add equipment |
| PATCH | `/equipment/{equipment_id}` | Update equipment fields |
| DELETE | `/equipment/{equipment_id}` | Remove equipment if it has no active loans |
| GET | `/loans` | List loans |
| POST | `/loans` | Create a loan |
| PATCH | `/loans/{loan_id}` | Change loan dates |
| POST | `/loans/{loan_id}/cancel` | Cancel a loan |
| GET | `/equipment/search?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | Find equipment available for a date range |

### Example API request bodies

Create equipment:
```json
{"name": "Laptop", "description": "Dell laptop"}
```

Create a loan:
```json
{"equipment_id": 1, "start_date": "2026-11-01", "end_date": "2026-11-05"}
```

Update a loan:
```json
{"end_date": "2026-11-06"}
```

## 6. Business rules

1. Equipment names cannot be empty.
2. Dates must be valid ISO dates, and the end date cannot precede the start date.
3. An equipment item cannot have two active loans with overlapping dates.
4. Cancelled loans remain in the database for history and do not block availability.
5. Equipment with active loans cannot be deleted.
6. Equipment search excludes any item whose active loan overlaps the requested date range.

