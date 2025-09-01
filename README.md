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
python src/etl.py

# Kör tester
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