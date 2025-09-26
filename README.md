# ETL-finance

ETL-finance är en minimal portfölj-tracker som demonstrerar:
1. ETL-flöde för aktiekurser via [yfinance](https://pypi.org/project/yfinance/).
2. Databas i SQLite för att lagra prisdata och trades.
3. Streamlit-app för att visualisera portföljutveckling, registrera affärer och jämföra mot OMXSPI.

# Funktioner

- ETL-jobb som hämtar aktiekurser och lagrar i SQLite (src/etl.py).
- Trades – registrera köp/sälj med pris, datum och eventuell courtage.
- Portföljöversikt – se innehav, GAV, och total portföljutveckling.
- Graf – jämför din portföljutveckling mot OMXSPI över olika perioder.
- Demo-login.

# Kom igång

```powershell
# Klona repo och skapa miljö
git clone https://github.com/<ditt-användarnamn>/ETL-finance.git
cd ETL-finance

python -m venv venv
.\venv\Scripts\activate

# Installera beroenden
pip install -r requirements.txt

# för att köra lokalt:
python -m streamlit run app/streamlit_app.py

# Kör ETL-skriptet
# Detta fyller tabellen prices i data/data.db med aktiekurser. Körs normalt regelbundet (t.ex. via schemaläggning).
python src/etl.py

# Kör tester 
# test_extract_shape: verifierar att funktionen extract() returnerar en DataFrame i rätt format (kolumnerna ts, ticker, close).
# test_load_inserts_into_temp_db: verifierar att funktionen load() kan skriva in data i en SQLite-databas och att raden går att läsa tillbaka.
pytest -v

# Schemaläggning (Windows)

Man kan schemalägga körningen via schemaläggaren:

Öppna schemaläggaren → Åtgärder → Ny. Välj sedan scriptet och när det ska köras    


# Projektstruktur

etl-finance/
├─ app/                           # Streamlit-applikationen
│  ├─ config.py                   # Centrala inställningar (DB_PATH, START_CASH, DEMO_USER/PASS)
│  ├─ streamlit_app.py            # Entry-point för Streamlit
│  ├─ pages/                      # Sidor i Streamlit
│  │  ├─ 1_Dashboard.py           # Översikt, grafer, KPI:er
│  │  ├─ 2_Trades.py              # Registrera och lista trades
│  │  └─ 3_Models.py              # Placeholder för framtida modeller
│  └─ services/                   # Tjänstelager
│     ├─ db.py                    # Databaskoppling, schema
│     ├─ trades.py                # Trades-funktioner
│     ├─ portfolio.py             # Portföljberäkningar (GAV, PnL, cash)
│     ├─ universe.py              # Laddar och söker i universet (CSV)
│     ├─ auth.py                  # Enkel inloggning
│     └─ backfill_prices.py       # (tillval) backfill av prisdata
│
├─ src/
│  └─ etl.py                      # ETL-jobb för aktiekurser
│
├─ data/
│  ├─ omx_securities.csv          # Univers av aktier (bör laddas upp i repo)
│  └─ data.db                     # SQLite DB (IGNORERAS i git)
│
├─ logs/                          # Loggar (IGNORERAS i git)
│  └─ etl.log
│
├─ tests/
│  └─ test_etl.py                 # Pytest för extract() och load()
│
├─ .env.example                   # Demo credentials, START_CASH
├─ .gitignore
├─ requirements.txt
├─ pytest.ini
└─ README.md

```

# Data

- Databas: SQLite, sparas som data/data.db.
- Universe: CSV-fil (data/omx_securities.csv) med name_display, yf_symbol, segment.
- Loggar: logs/etl.log.

# Begränsningar & vidareutveckling

- Ingen riktig användarhantering (bara demo-login).
- ETL körs manuellt (schemaläggning får sättas upp separat). I en vidareutveckling laddas DB upp på moln. 
- Endast grundläggande portföljlogik (GAV, TWR).
- Ingen hantering av utdelningar.