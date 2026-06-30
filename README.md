# Resume Transformer (`transformer.py`)

A Python-based resume parsing, validation, and data consolidation utility. This script extracts information from candidate resumes (PDF format), normalizes data (e.g., telephone numbers to E.164, locations to ISO 3166-1 alpha-2, GitHub profile data), cross-references and merges it with structured data from a CSV, filters or projects specific fields based on custom configuration, and saves the consolidated result as a JSON file.

---

## Features

- **PDF Parsing**: Extracts text from PDF files using `pypdf`.
- **Flexible Extraction Methods**:
  - **Regex Mode**: Fast, lightweight extraction of email, phone, links, and programming skills based on pre-defined lists.
  - **AI Mode**: Advanced semantic parsing of experience, education, skills, and contacts using Ollama LLM (`minimax-m2.5:cloud` model).
- **GitHub Integration**: Automatically retrieves candidate public name, bio, and repository list from the GitHub API using a matching profile link.
- **CSV Lookup & Merging**: Cross-references parsed resume details with a master candidates list using email/phone matching.
- **Normalization**:
  - Normalizes telephone numbers to the standard **E.164** format using `phonenumbers`.
  - Resolves location names to **ISO 3166-1 alpha-2** country codes using `pycountry`.
- **Quality-Based De-duplication**: Retains the highest-quality candidate data record when duplicate profiles are detected.
- **Data Projection & Custom Fields Schema**: Uses a declarative JSON config to filter, map, rename, enforce types, and require specific fields.
- **Provenance Tracking**: Captures the source origin of each populated data field (CSV row index/column, PDF filename, etc.).

---

## Installation & Setup

Ensure you have Python 3.8+ installed.

### 1. Install Dependencies

Install the required Python packages:

```bash
pip install pypdf pycountry phonenumbers
```

If you plan to use the **AI Mode** (`--ai`), install the `ollama` package and ensure the local Ollama instance is configured:

```bash
pip install ollama
```

### 2. (Optional) GitHub Token Config

To prevent GitHub API rate limiting during profile enrichment, set your personal access token in your environment variables:

```bash
# Windows (PowerShell)
$env:GITHUB_TOKEN="your_personal_access_token_here"

# Linux / macOS / Git Bash
export GITHUB_TOKEN="your_personal_access_token_here"
```

---

## Usage

Run the script from your terminal using:

```bash
python transformer.py <dir_path> <csv_path> [options]
```

### Positional Arguments
- `dir_path`: Absolute or relative path to the directory containing candidate resume PDFs (e.g., `assets/resumes`).
- `csv_path`: Path to the CSV metadata file (e.g., `assets/candidates.csv`).

### Optional Flags
- `--ai`: Enable LLM-based extraction via Ollama (defaults to Regex parser if not set).
- `--config <path_to_config>`: Path to a JSON configuration file defining the output data structure/projection.

---

## Examples

### 1. Basic Run (Regex Parsing)

Processes all resumes in `./assets/resumes` matching against `./assets/candidates.csv`, generating standard consolidated JSON:

```bash
python transformer.py ./assets/resumes ./assets/candidates.csv
```

### 2. AI-Assisted Parsing

Uses the Ollama LLM to parse detailed structure (experience/education):

```bash
python transformer.py ./assets/resumes ./assets/candidates.csv --ai
```

### 3. Running with a Custom Projection Config

Restricts the output keys, renames fields, enforces data types, and normalizes phone numbers using a config file:

```bash
python transformer.py ./assets/resumes ./assets/candidates.csv --config config.json
```

---

## Configuration File Structure (`config.json`)

The `--config` flag allows you to shape the resulting JSON structure. You can map, type-validate, and mark fields as required.

### Example Config

```json
{
  "fields": [
    { "path": "candidate_id", "type": "string", "required": true },
    { "path": "full_name", "type": "string", "required": true },
    { "path": "emails", "from": "emails[0]", "type": "string", "required": true},
    { "path": "phones", "from": "phones", "type": "string", "normalize": true }
  ],
  "include_provenance": false,
  "on_missing": "null"
}
```

### Configuration Options
- `fields`: A list of object definitions:
  - `path`: The key name in the final output.
  - `from` *(optional)*: The source key/path in the internal canonical candidate payload (e.g., `emails[0]` to fetch only the first email). Defaults to `path`.
  - `type` *(optional)*: Enforces value validation (`string`, `array`, `object`, `boolean`, `number`).
  - `required` *(optional)*: If `true`, candidates lacking this field will be skipped.
  - `normalize` *(optional)*: Specifically formats phone numbers.
- `include_provenance`: If `true`, injects a `"provenance"` field tracking where the data originated.
- `on_missing`: Specifies behavior if a field is missing or has a type mismatch:
  - `"null"` (default): Sets the value to `null`.
  - `"omit"`: Excludes the key entirely from the output object.
  - `"error"`: Raises an error and halts execution.

---

## Outputs

Consolidated results are saved automatically to `out/result.json`.

Example candidate record in `result.json`:

```json
{
  "candidate_id": "CAND00000001",
  "full_name": "Ayushmaan Padhi",
  "emails": [
    "mygmail@gmail.com",
    "padhiayushmaan@gmail.com"
  ],
  "phones": [
    "1234567890",
    "+919337158919"
  ],
  "normalized_phones": [
    "+911234567890",
    "+919337158919"
  ],
  "location": "IN",
  "links": [
    "https://github.com/example_user"
  ],
  "skills": [
    "python",
    "git"
  ],
  "experience": null,
  "education": null,
  "github_profile_data": {
    "name": "Ayushmaan Padhi",
    "bio": "Software Engineer",
    "repositories": [
      {
        "html_url": "https://github.com/example_user/repo1",
        "language": "Python"
      }
    ]
  },
  "provenance": [
    { "field": "candidate_id", "source": "CSV: Row 2; Column candidate_id" },
    { "field": "full_name", "source": "CSV: Row 2; Column full_name" },
    { "field": "location", "source": "CSV: Row 2; Column location" },
    { "field": "emails", "source": "Resume: resume_ayushmaan.pdf" },
    ...
  ]
}
```
