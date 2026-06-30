import json
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

def extract_resume_data(resume_text):
    prompt = (
        "Extract the following information from the resume text below. "
        "Return a strict JSON object with these exact keys: "
        "'emails' (list of strings), 'phones' (list of strings), 'links' (list of Github Profile and LinkedIn URLs), "
        "'years_experience' (float or null, note: this will automatically be calculated based on the time periods in the experience section), 'skills' (list of strings), "
        "'experience' (list of objects, where each object has 'role' (string), 'start_date' (MM-DD-YYYY), 'end_date' (MM-DD-YYYY), 'company' (string), and 'summary' (string)), "
        "'education_background' (list of objects, where each object has 'degree' (string), 'institution' (string), and 'summary' (string)). \n\n"
        "Resume Text: \n" + resume_text
    )

    response = ollama.chat(
        model="minimax-m2.5:cloud",
        messages=[{"role": "user", "content": prompt}],
        format="json",
        think=False
    )
    
    return json.loads(response.message.content)

def main():
    resume_text = read_pdf("C:/Users/ayu2805/Documents/mscdt/assets/resumes/Ayushmaan Padhi.pdf")
    json_data = extract_resume_data(resume_text)
    
    with open("result.json", "w") as file:
        json.dump(json_data, file, indent=4)

if __name__ == "__main__":
    main()