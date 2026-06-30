import argparse
import json
import re
import urllib.request
import urllib.error
import ollama
import pypdf

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
    headers = {"User-Agent": "Python-Urllib-Resume-Parser"}
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true")
    args = parser.parse_args()

    resume_text = read_pdf("C:/Users/ayu2805/Documents/mscdt/assets/resumes/Ayushmaan Padhi.pdf")
    
    if args.ai:
        json_data = extract_resume_data_ai(resume_text)
    else:
        json_data = extract_resume_data_regex(resume_text)
        
    github_username = extract_github_username(json_data.get("links", []))
    if github_username:
        json_data["github_profile_data"] = fetch_github_data(github_username)
    else:
        json_data["github_profile_data"] = None
        
    with open("out/result.json", "w") as file:
        json.dump(json_data, file, indent=4)

if __name__ == "__main__":
    main()