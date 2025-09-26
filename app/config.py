from pathlib import Path

# Dessa typer av uppgifter hade lagts upp i en fil som "secrets" eller .env vid en riktig tillämpning
# För denna demo hålls detta öppet dock.

# Projektrot
ROOT = Path(__file__).resolve().parents[1]

# Databas & loggar 
DB_PATH = ROOT / "data" / "data.db"
APP_LOG = ROOT / "logs" / "app.log"

# Demo-login (läggs i .env senare)
DEMO_USER = "demo"
DEMO_PASS = "demo123"

# Startkapital i SEK
START_CASH = 1_000_000.0