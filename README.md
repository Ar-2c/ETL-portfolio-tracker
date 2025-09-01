# ETL-yfinance

Ett litet **proof-of-concept** för att:
1. Hämta aktiekurser via [yfinance](https://pypi.org/project/yfinance/).
2. Transformera datan till rätt format.
3. Spara i en **SQLite-databas**.

---

# Kom igång

```powershell
# Klona repot
git clone https://github.com/Ar-2c/ETL-yfinance.git
cd ETL-finance

# Skapa virtuell miljö
python -m venv venv
.\venv\Scripts\Activate

# Installera beroenden
pip install -r requirements.txt

# Kör ETL-skriptet
# Extract: hämtar aktiekurser (closing prices) via yfinance.
# Transform: säkerställer att datan får rätt format (datum, ticker, closing-pris).
# Load: sparar datan i en SQLite-databas (data/data.db) och loggar resultatet i logs/etl.log.
python src/etl.py

# Kör tester 
# test_extract_shape: verifierar att funktionen extract() returnerar en DataFrame i rätt format (kolumnerna ts, ticker, close).
# test_load_inserts_into_temp_db: verifierar att funktionen load() kan skriva in data i en SQLite-databas och att raden går att läsa tillbaka.
pytest -v

# Schemaläggning (Windows)

Man kan schemalägga körningen via schemaläggaren:

Öppna schemaläggaren → Åtgärder → Ny. Välj sedan scriptet och när det ska köras    


# Projektstruktur

ETL-finance/
├── data/          # SQLite-databas
├── logs/          # Loggfiler
├── src/           # ETL-skript
├── tests/         # Tester
├── venv/          # Virtuell miljö (ignoreras av git)
├── requirements.txt
├── .gitignore
└── README.md