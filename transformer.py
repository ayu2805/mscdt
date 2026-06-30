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
        "emails": emails,
        "phones": phones,
        "links": links,
        "skills": skills if skills else None,
        "years_experience": None,
        "experience": None,
        "education_background": None
    }

def extract_resume_data_ai(resume_text):
    prompt = (
        "Extract the following information from the resume text below. "
        "Return a strict JSON object with these exact keys: "
        "'emails' (list of strings), 'phones' (list of strings), 'links' (list of Github Profile and LinkedIn URLs), "
        "'years_experience' (float or null, note: this will automatically be calculated based on the time periods in the experience section), 'skills' (list of strings or null), "
        "'experience' (list of objects or null, where each object has 'role' (string), 'start_date' (MM-DD-YYYY), 'end_date' (MM-DD-YYYY), 'company' (string), and 'summary' (string)), "
        "'education_background' (list of objects or null, where each object has 'degree' (string), 'institution' (string), and 'summary' (string)). \n"
        "If years_experience, skills, experience, or education_background are not found or cannot be extracted, set their values to null. \n\n"
        "Resume Text: \n" + resume_text
    )

    response = ollama.chat(
        model="minimax-m2.5:cloud",
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0.0}
    )
    
    data = json.loads(response.message.content)
    
    fixed_keys = ["years_experience", "skills", "experience", "education_background"]
    for key in fixed_keys:
        if key not in data or not data[key]:
            data[key] = None
            
    return data

def calculate_data_quality(data):
    score = 0
    for key in ["skills", "experience", "education_background"]:
        val = data.get(key)
        if isinstance(val, list):
            score += len(val)
    if data.get("years_experience") is not None:
        score += 1
    if data.get("github_profile_data"):
        score += 1
    return score

def load_csv_data(csv_path):
    csv_lookup = {"by_email": {}, "by_phone": {}, "all_payloads": []}
    if not os.path.exists(csv_path):
        return csv_lookup

    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidate_id = row.get('candidate_id', '').strip()
            full_name = row.get('full_name', '').strip()
            location = row.get('location', '').strip()
            
            emails = [e.strip().lower() for e in row.get('emails', '').split(',') if e.strip()]
            phones = [p.strip() for p in row.get('phones', '').split(',') if p.strip()]
            
            payload = {
                "candidate_id": candidate_id,
                "full_name": full_name,
                "location": location,
                "emails": emails,
                "phones": phones
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
    try:
        parsed_number = phonenumbers.parse(phone_string, country_code)
        if phonenumbers.is_valid_number(parsed_number):
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return phone_string

def reorder_keys(data):
    ordered = {}
    for k in ["candidate_id", "full_name", "emails", "phones", "location",
              "links", "skills", "years_experience", "experience", "education_background",
              "github_profile_data"]:
        if k in data:
            ordered[k] = data[k]
    for k in data:
        if k not in ordered:
            ordered[k] = data[k]
    return ordered

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir_path", help="Path to the directory containing PDF resumes")
    parser.add_argument("csv_path", help="Path to the CSV file containing supplemental candidate data")
    parser.add_argument("--ai", action="store_true", help="Use AI-driven extraction instead of regex")
    args = parser.parse_args()

    if not os.path.isdir(args.dir_path):
        print(f"Error: {args.dir_path} is not a valid directory.")
        return

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

            resume_emails = [e.lower() for e in json_data.get("emails", [])]
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
                    csv_emails = matched_payload["emails"]
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
                        csv_emails = matched_payload["emails"]
                        csv_phones = matched_payload["phones"]
                        matched = True
                        break

            if matched_payload:
                matched_csv_payloads.add(id(matched_payload))

            country_iso = get_iso_alpha2(location_csv)
            
            json_data["candidate_id"] = candidate_id_csv
            json_data["full_name"] = full_name_csv
            json_data["location"] = country_iso if country_iso else location_csv

            target_emails = set(resume_emails)
            for e in csv_emails:
                target_emails.add(e.lower())
            json_data["emails"] = sorted(list(target_emails))

            target_phones = set(resume_phones)
            for p in csv_phones:
                target_phones.add(p)
            
            formatted_phones = set()
            for phone in target_phones:
                formatted_phones.add(format_e164(phone, country_iso))
            json_data["phones"] = sorted(list(formatted_phones))

            emails_key = tuple(sorted(list(target_emails)))
            
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

            unmatched_json_data = {
                "candidate_id": payload["candidate_id"],
                "full_name": payload["full_name"],
                "emails": sorted([e.lower() for e in payload["emails"]]),
                "phones": sorted(list(formatted_phones)),
                "location": country_iso if country_iso else payload["location"],
                "links": [],
                "skills": None,
                "years_experience": None,
                "experience": None,
                "education_background": None,
                "github_profile_data": None
            }
            
            emails_key = tuple(sorted([e.lower() for e in payload["emails"]]))
            if emails_key and emails_key not in unique_candidates:
                unique_candidates[emails_key] = unmatched_json_data

    all_students_data = [reorder_keys(v) for v in unique_candidates.values()]

    os.makedirs("out", exist_ok=True)
    with open("out/result.json", "w") as file:
        json.dump(all_students_data, file, indent=4)
        
    print(f"Successfully saved data for {len(all_students_data)} unique students to out/result.json")

if __name__ == "__main__":
    main()