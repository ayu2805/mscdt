import argparse
import json
import re
import urllib.request
import urllib.error
import os
import glob
import csv
import ollama
import pypdf
import pycountry
import phonenumbers

def read_pdf(file_path):
    reader = pypdf.PdfReader(file_path)
    full_text = []
    
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text.append(text)
            
    return "\n".join(full_text)

def extract_github_username(links):
    for link in links:
        match = re.search(r'github\.com/([a-zA-Z0-9\-]+)', link, re.IGNORECASE)
        if match:
            username = match.group(1)
            if username.lower() not in ['settings', 'repositories', 'explore', 'trending']:
                return username
    return None

def fetch_github_data(username):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Python-Urllib-Resume-Parser"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    github_data = {"name": None, "bio": None, "repositories": []}
    
    try:
        user_req = urllib.request.Request(f"https://api.github.com/users/{username}", headers=headers)
        with urllib.request.urlopen(user_req) as response:
            user_info = json.loads(response.read().decode())
            github_data["name"] = user_info.get("name")
            github_data["bio"] = user_info.get("bio")
    except urllib.error.URLError:
        pass

    try:
        repos_req = urllib.request.Request(f"https://api.github.com/users/{username}/repos", headers=headers)
        with urllib.request.urlopen(repos_req) as response:
            repos_info = json.loads(response.read().decode())
            for repo in repos_info:
                github_data["repositories"].append({
                    "html_url": repo.get("html_url"),
                    "language": repo.get("language")
                })
    except urllib.error.URLError:
        pass

    return github_data

def is_valid_email_format(email):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))

def extract_resume_data_regex(resume_text):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'\+?\d[\d\-\s\(\)]{8,}\d'
    link_pattern = r'\b(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com)[^\s]*'
    
    emails = list(set(re.findall(email_pattern, resume_text)))
    phones = list(set(re.findall(phone_pattern, resume_text)))
    raw_links = re.findall(link_pattern, resume_text)

    normalized_links = set()
    for link in raw_links:
        github_match = re.search(r'(?:github\.com)/([a-zA-Z0-9\-]+)', link, re.IGNORECASE)
        if github_match:
            username = github_match.group(1)
            normalized_links.add(f"https://github.com/{username}")
        else:
            if not link.startswith(('http://', 'https://')):
                link = 'https://' + link
            normalized_links.add(link.rstrip('/.,-'))
            
    links = list(normalized_links)
    
    common_skills = [
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust", "ruby", "php",
        "sql", "nosql", "postgresql", "mongodb", "mysql", "redis",
        "html", "css", "react", "angular", "vue", "next.js", "node.js", "express", "django", "flask", "fastapi",
        "aws", "azure", "gcp", "docker", "kubernetes", "cicd", "jenkins", "git", "github",
        "machine learning", "deep learning", "nlp", "data science", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
        "linux", "bash", "rest api", "graphql", "agile", "scrum"
    ]
    
    skills = []
    for skill in common_skills:
        escaped_skill = re.escape(skill)
        pattern = rf'\b{escaped_skill}\b'
        if skill in ["c++", "c#", "node.js", "next.js"]:
            pattern = rf'(?:^|[\s,.\-\/]){escaped_skill}(?:$|[\s,.\-\/])'
            
        if re.search(pattern, resume_text, re.IGNORECASE):
            skills.append(skill)
            
    return {
        "emails": emails if emails else [None],
        "phones": phones,
        "links": links,
        "skills": skills if skills else None,
        "experience": None,
        "education": None
    }

def extract_resume_data_ai(resume_text):
    prompt = (
        "Extract the following information from the resume text below. "
        "Return a strict JSON object with these exact keys: "
        "'emails' (list of strings), 'phones' (list of strings), 'links' (list of Github Profile and LinkedIn URLs), "
        "'skills' (list of strings or null), "
        "'experience' (list of objects or null, where each object has 'role' (string), 'start_date' (MM-DD-YYYY), 'end_date' (MM-DD-YYYY), 'company' (string), and 'summary' (string)), "
        "'education' (list of objects or null, where each object has 'degree' (string), 'institution' (string), and 'summary' (string)). \n"
        "If skills, experience, or education are not found or cannot be extracted, set their values to null. \n"
        "Ensure all email entries in the 'emails' array strictly match standard email formats. If an email is improperly formatted or invalid, exclude it from the list.\n\n"
        "Resume Text: \n" + resume_text
    )

    response = ollama.chat(
        model="minimax-m2.5:cloud",
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0.0}
    )
    
    data = json.loads(response.message.content)
    
    fixed_keys = ["skills", "experience", "education"]
    for key in fixed_keys:
        if key not in data or not data[key]:
            data[key] = None
            
    if "emails" in data and isinstance(data["emails"], list):
        valid_emails = [e for e in data["emails"] if is_valid_email_format(str(e))]
        data["emails"] = valid_emails if valid_emails else [None]
    else:
        data["emails"] = [None]
            
    return data

def calculate_data_quality(data):
    score = 0
    for key in ["skills", "experience", "education"]:
        val = data.get(key)
        if isinstance(val, list):
            score += len(val)
    if data.get("github_profile_data"):
        score += 1
    return score

def load_csv_data(csv_path):
    csv_lookup = {"by_email": {}, "by_phone": {}, "all_payloads": []}
    if not os.path.exists(csv_path):
        return csv_lookup

    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            candidate_id = row.get('candidate_id', '').strip()
            full_name = row.get('full_name', '').strip()
            location = row.get('location', '').strip()
            
            emails = [e.strip().lower() for e in row.get('emails', '').split(',') if e.strip() and is_valid_email_format(e.strip())]
            phones = [p.strip() for p in row.get('phones', '').split(',') if p.strip()]
            
            payload = {
                "candidate_id": candidate_id,
                "full_name": full_name,
                "location": location,
                "emails": emails if emails else [None],
                "phones": phones,
                "row_index": idx
            }
            
            csv_lookup["all_payloads"].append(payload)
            
            for email in emails:
                if email not in csv_lookup["by_email"]:
                    csv_lookup["by_email"][email] = []
                csv_lookup["by_email"][email].append(payload)
                
            for phone in phones:
                if phone not in csv_lookup["by_phone"]:
                    csv_lookup["by_phone"][phone] = []
                csv_lookup["by_phone"][phone].append(payload)
                
    return csv_lookup

def get_iso_alpha2(location_string):
    if not location_string:
        return None
    try:
        country = pycountry.countries.search_fuzzy(location_string)[0]
        return country.alpha_2
    except LookupError:
        return None

def format_e164(phone_string, country_code):
    if not phone_string:
        return None
        
    cleaned_digits = re.sub(r'\D', '', phone_string)
    digit_count = len(cleaned_digits)
    
    if not (2 < digit_count < 16):
        return phone_string
        
    try:
        parsed_number = phonenumbers.parse(phone_string, country_code)
        return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        if country_code and not phone_string.startswith('+'):
            try:
                from phonenumbers.phonenumberutil import country_code_for_region
                calling_code = country_code_for_region(country_code)
                if calling_code > 0:
                    alt_parsed = phonenumbers.parse(f"+{calling_code}{phone_string}", None)
                    return phonenumbers.format_number(alt_parsed, phonenumbers.PhoneNumberFormat.E164)
            except Exception:
                pass
    return phone_string

def resolve_path(data, path):
    if not path:
        return data
    parts = re.split(r'\[|\]\.|\]', path)
    parts = [p for p in parts if p]
    current = data
    for part in parts:
        if current is None:
            return None
        if isinstance(current, list):
            if part.isdigit():
                idx = int(part)
                if idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                current = [item.get(part) for item in current if isinstance(item, dict) and part in item]
                if not current:
                    return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current

def validate_type(value, expected_type):
    if value is None:
        return True
    if expected_type == "string":
        if isinstance(value, str):
            return True
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return True
    if expected_type == "array" and isinstance(value, list):
        return True
    if expected_type == "object" and isinstance(value, dict):
        return True
    if expected_type == "boolean" and isinstance(value, bool):
        return True
    if expected_type == "number" and isinstance(value, (int, float)):
        return True
    return False

def apply_projection(canonical_data, config):
    if not config:
        return canonical_data
    
    projected_data = {}
    on_missing = config.get("on_missing", "null")
    
    for field_def in config.get("fields", []):
        target_path = field_def.get("path")
        source_path = field_def.get("from", target_path)
        expected_type = field_def.get("type")
        normalize = field_def.get("normalize", False)
        
        if source_path.startswith("phones") and normalize:
            source_path = source_path.replace("phones", "normalized_phones")
            
        value = resolve_path(canonical_data, source_path)
        
        if value is None or (isinstance(value, list) and not any(value)):
            if on_missing == "error":
                raise ValueError(f"Missing value for field: {target_path}")
            elif on_missing == "omit":
                continue
            else:
                projected_data[target_path] = None
        else:
            if expected_type and not validate_type(value, expected_type):
                if on_missing == "error":
                    raise TypeError(f"Type mismatch for {target_path}. Expected {expected_type}.")
                elif on_missing == "omit":
                    continue
                else:
                    projected_data[target_path] = None
            else:
                projected_data[target_path] = value
                
    if config.get("include_provenance", False):
        projected_data["provenance"] = canonical_data.get("provenance")
        
    return projected_data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir_path")
    parser.add_argument("csv_path")
    parser.add_argument("--ai", action="store_true")
    parser.add_argument("--config", help="Path to JSON config file for projection")
    args = parser.parse_args()

    if not os.path.isdir(args.dir_path):
        print(f"Error: {args.dir_path} is not a valid directory.")
        return

    config = None
    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)

    pdf_files = glob.glob(os.path.join(args.dir_path, "*.pdf"))
    csv_lookup = load_csv_data(args.csv_path)
    unique_candidates = {}
    matched_csv_payloads = set()

    for file_path in pdf_files:
        filename = os.path.basename(file_path)
        print(f"Processing: {filename}")

        try:
            resume_text = read_pdf(file_path)
            
            if args.ai:
                json_data = extract_resume_data_ai(resume_text)
            else:
                json_data = extract_resume_data_regex(resume_text)
                
            github_username = extract_github_username(json_data.get("links", []))
            if github_username:
                json_data["github_profile_data"] = fetch_github_data(github_username)
            else:
                json_data["github_profile_data"] = None

            resume_emails = [e.lower() for e in json_data.get("emails", []) if e and is_valid_email_format(e)]
            resume_phones = json_data.get("phones", []) if json_data.get("phones") else []

            candidate_id_csv = None
            full_name_csv = None
            location_csv = None
            csv_emails = []
            csv_phones = []
            matched = False
            matched_payload = None

            for email in resume_emails:
                if email in csv_lookup["by_email"]:
                    matched_payload = csv_lookup["by_email"][email][0]
                    candidate_id_csv = matched_payload["candidate_id"]
                    full_name_csv = matched_payload["full_name"]
                    location_csv = matched_payload["location"]
                    csv_emails = [e for e in matched_payload["emails"] if e]
                    csv_phones = matched_payload["phones"]
                    matched = True
                    break

            if not matched:
                for phone in resume_phones:
                    if phone in csv_lookup["by_phone"]:
                        matched_payload = csv_lookup["by_phone"][phone][0]
                        candidate_id_csv = matched_payload["candidate_id"]
                        full_name_csv = matched_payload["full_name"]
                        location_csv = matched_payload["location"]
                        csv_emails = [e for e in matched_payload["emails"] if e]
                        csv_phones = matched_payload["phones"]
                        matched = True
                        break

            provenance = []

            if candidate_id_csv:
                provenance.append({"field": "candidate_id", "source": f"CSV: Row {matched_payload['row_index']}; Column candidate_id"})
            else:
                provenance.append({"field": "candidate_id", "source": "not_in_csv"})

            if full_name_csv:
                provenance.append({"field": "full_name", "source": f"CSV: Row {matched_payload['row_index']}; Column full_name"})
            else:
                provenance.append({"field": "full_name", "source": "not_in_csv"})

            if location_csv:
                provenance.append({"field": "location", "source": f"CSV: Row {matched_payload['row_index']}; Column location"})
            else:
                provenance.append({"field": "location", "source": "not_in_csv"})

            if resume_emails:
                provenance.append({"field": "emails", "source": f"Resume: {filename}"})
            elif csv_emails:
                provenance.append({"field": "emails", "source": f"CSV: Row {matched_payload['row_index']}; Column emails"})
            else:
                provenance.append({"field": "emails", "source": "not_in_resume"})

            if resume_phones:
                provenance.append({"field": "phones", "source": f"Resume: {filename}"})
            elif csv_phones:
                provenance.append({"field": "phones", "source": f"CSV: Row {matched_payload['row_index']}; Column phones"})
            else:
                provenance.append({"field": "phones", "source": "not_in_resume"})

            for field in ["links", "skills", "experience", "education"]:
                if json_data.get(field):
                    provenance.append({"field": field, "source": f"Resume: {filename}"})
                else:
                    provenance.append({"field": field, "source": "not_in_resume"})

            json_data["provenance"] = provenance

            if matched_payload:
                matched_csv_payloads.add(id(matched_payload))

            country_iso = get_iso_alpha2(location_csv)
            
            json_data["candidate_id"] = candidate_id_csv
            json_data["full_name"] = full_name_csv
            json_data["location"] = country_iso if country_iso else location_csv

            target_emails = set(resume_emails)
            for e in csv_emails:
                if e and is_valid_email_format(e):
                    target_emails.add(e.lower())
            
            final_emails = sorted(list(target_emails))
            json_data["emails"] = final_emails if final_emails else [None]

            target_phones = set(resume_phones)
            for p in csv_phones:
                target_phones.add(p)
            
            json_data["phones"] = sorted(list(target_phones))
            formatted_phones = set()
            for phone in target_phones:
                formatted_phones.add(format_e164(phone, country_iso))
            json_data["normalized_phones"] = sorted(list(formatted_phones))

            emails_key = tuple(sorted([e for e in final_emails if e]))
            
            if not emails_key:
                candidate_key = (filename,)
            else:
                candidate_key = (emails_key,)

            if candidate_key in unique_candidates:
                existing_data = unique_candidates[candidate_key]
                if calculate_data_quality(json_data) > calculate_data_quality(existing_data):
                    unique_candidates[candidate_key] = json_data
            else:
                unique_candidates[candidate_key] = json_data
            
        except Exception as e:
            print(f"Failed to process {filename}: {e}")

    for payload in csv_lookup["all_payloads"]:
        if id(payload) not in matched_csv_payloads:
            country_iso = get_iso_alpha2(payload["location"])
            formatted_phones = set()
            for phone in payload["phones"]:
                formatted_phones.add(format_e164(phone, country_iso))

            payload_emails = [e.lower() for e in payload["emails"] if e and is_valid_email_format(e)]

            unmatched_provenance = [
                {"field": "candidate_id", "source": f"CSV: Row {payload['row_index']}; Column candidate_id" if payload["candidate_id"] else "not_in_csv"},
                {"field": "full_name", "source": f"CSV: Row {payload['row_index']}; Column full_name" if payload["full_name"] else "not_in_csv"},
                {"field": "emails", "source": f"CSV: Row {payload['row_index']}; Column emails" if payload_emails else "not_in_csv"},
                {"field": "phones", "source": f"CSV: Row {payload['row_index']}; Column phones" if formatted_phones else "not_in_csv"},
                {"field": "location", "source": f"CSV: Row {payload['row_index']}; Column location" if payload["location"] else "not_in_csv"},
                {"field": "links", "source": "not_in_resume"},
                {"field": "skills", "source": "not_in_resume"},
                {"field": "experience", "source": "not_in_resume"},
                {"field": "education", "source": "not_in_resume"}
            ]

            unmatched_json_data = {
                "candidate_id": payload["candidate_id"],
                "full_name": payload["full_name"],
                "emails": sorted(payload_emails) if payload_emails else [None],
                "phones": sorted(payload["phones"]),
                "normalized_phones": sorted(list(formatted_phones)),
                "location": country_iso if country_iso else payload["location"],
                "links": [],
                "skills": None,
                "experience": None,
                "education": None,
                "github_profile_data": None,
                "provenance": unmatched_provenance
            }
            
            emails_key = tuple(sorted(payload_emails))
            if emails_key and emails_key not in unique_candidates:
                unique_candidates[emails_key] = unmatched_json_data
            elif not emails_key:
                unique_candidates[(payload["candidate_id"],)] = unmatched_json_data

    all_students_data = []
    for v in unique_candidates.values():
        try:
            projected = apply_projection(v, config)
            all_students_data.append(projected)
        except Exception as e:
            print(f"Projection error: {e}")

    os.makedirs("out", exist_ok=True)
    with open("out/result.json", "w") as file:
        json.dump(all_students_data, file, indent=4)
        
    print(f"Successfully saved data for {len(all_students_data)} unique students to out/result.json")

if __name__ == "__main__":
    main()