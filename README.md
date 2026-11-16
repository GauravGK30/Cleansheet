# CleanSheet

CleanSheet is a privacy-focused spreadsheet cleaning tool for cleaning and standardizing CSV and Excel files using rule-based processing.

## Features

- CSV and XLSX file processing
- Data profiling and validation
- Missing value handling
- Duplicate detection
- Data type conversion
- Text standardization
- Find and replace
- Data cleaning preview
- Custom cleaning rules
- Export cleaned files
- No AI or external AI APIs

## Tech Stack

- Python
- FastAPI
- Pandas
- OpenPyXL
- HTML, CSS, JavaScript
- Pytest

## Run Locally

```bash
git clone https://github.com/GauravGK30/Cleansheet.git
cd Cleansheet

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
python run.py
```

Then open the local URL shown in the terminal.

## Project Structure

```text
app/
├── api/
├── core/
├── static/
├── templates/
└── main.py

tests/
scripts/
run.py
requirements.txt
```
