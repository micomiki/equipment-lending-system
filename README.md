# Equipment Lending

A small Python project implementing the Equipment Lending assignment with:
- Python Programming language
- A SQLite database.
- Without graphical user interface.
- A REST API documented automatically by FastAPI.

## 1. Requirements

- Python 3.10 or high
- pip

## 2. Install

Create and activate a virtual environment.

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

***Equipment Commands***
python lending.py equipment list
python lending.py equipment add --name "Laptop" --description "Dell Laptop"
python lending.py equipment add --name "Projector" --description "HDMI Projector"
python lending.py equipment update 1 --name "HP Laptop"
python lending.py equipment update 1 --description "HP Laptop, 16 GB RAM"
python lending.py equipment update 1 --name "HP Laptop" --description "16 GB RAM"
python lending.py equipment remove 2
python lending.py equipment search --from 2026-11-01 --to 2026-11-05

The numbers are equipment IDs. Use equipment list to find the correct IDs.


***Loan Commands***
python lending.py loan list
python lending.py loan create --equipment 1 --from 2026-11-01 --to 2026-11-05
python lending.py loan change 1 --from 2026-11-02
python lending.py loan change 1 --to 2026-11-06
python lending.py loan change 1 --from 2026-11-02 --to 2026-11-06
python lending.py loan cancel 1


The number after loan change or loan cancel is the loan ID, not the equipment ID.

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
2. Dates must be valid ISO dates, and the end date cannot Before the start date.
3. An equipment item cannot have two active loans with overlapping dates.
4. Cancelled loans remain in the database for history until the Equipment exists and do not block availability.
5. Equipment with active loans cannot be deleted.
6. Equipment search excludes any item whose active loan overlaps the requested date range.


## 8. Running with Docker

Docker lets run the Equipment Lending System in a container without installing the project's Python dependencies directly on the computer.

### Step 1: Build the Docker image

Make sure Docker Desktop is running. Open a terminal in the project directory containing the `Dockerfile` and run:

```bash
docker build -t equipment-lending .
```

### Step 2: Create a persistent database volume

Create a Docker volume to store the SQLite database:

```bash
docker volume create equipment-lending-data
```

The volume preserves database data independently of the container's lifecycle.

### Step 3: Run the application

```bash
docker run -d --name equipment-lending -p 8000:8000 -v equipment-lending-data:/data equipment-lending
```

This command:

- Runs the application in the background.
- Maps port `8000` on the computer to port `8000` in the container.
- Mounts the persistent volume at `/data`.
- Uses `/data/lending.db` for the SQLite database inside the container.

### Step 4: Access the API

Open the interactive API documentation:

<http://localhost:8000/docs>

### Step 5: Test the CLI inside Docker

List equipment:

```bash
docker exec -it equipment-lending python lending.py equipment list
```

List loans:

```bash
docker exec -it equipment-lending python lending.py loan list
```

Add equipment:

```bash
docker exec -it equipment-lending python lending.py equipment add --name "Laptop" --description "Test laptop"
```

### Step 6: Manage the container

Check running containers:

```bash
docker ps
```

View application logs:

```bash
docker logs equipment-lending
```

Stop the container:

```bash
docker stop equipment-lending
```

Start the existing container again:

```bash
docker start equipment-lending
```

### Step 7: Update the Docker image after code changes

Rebuild the image:

```bash
docker build -t equipment-lending .
```

The existing container will not automatically switch to the newly built image. Stop and remove the old container, then create a new one:

```bash
docker stop equipment-lending
docker rm equipment-lending
docker run -d --name equipment-lending -p 8000:8000 -v equipment-lending-data:/data equipment-lending
```

The command reuses the existing `equipment-lending-data` volume, preserving its database data. Removing a container does not remove the named volume. Do not remove the volume if we need to keep its data.
