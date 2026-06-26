import pytesseract
from pdf2image import convert_from_path
import requests
import json
import time
import asyncio
import pypdf
import re

# Semaphore for local Ollama to prevent laptop crashes, this wont let all the threads to jump in at the same time.

ollama_semaphore = asyncio.Semaphore(1)

def extract_text_from_pdf(doc_path):
    """Phase 1: Hybrid Extraction with Smart Chunking."""
    extracted_chunks = []
    try:
        reader = pypdf.PdfReader(doc_path)
        for page_idx, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and len(text.strip()) > 50: 
                _chunk_text(text, page_idx, extracted_chunks)
            else:
                images = convert_from_path(doc_path, first_page=page_idx+1, last_page=page_idx+1)
                if images:

                    # Add more languages if you want.
                    # Currently, I have added the following languages:
                    # Peru (Spanish), Arabic, China, Italy, Singapore, Malaysia

                    ocr_text = pytesseract.image_to_string(images[0], lang="eng+spa+ara+chi_sim+ita+msa")
                    _chunk_text(ocr_text, page_idx, extracted_chunks)
    except Exception as e:
        print(f"Extraction error: {e}")
    return extracted_chunks

def _chunk_text(text, page_idx, extracted_chunks):
    """Cuts text into 1000-character pieces for deep context."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    CHUNK_SIZE = 1000  
    OVERLAP = 200     
    
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            extracted_chunks.append({"page": page_idx + 1, "text": chunk})
        start += (CHUNK_SIZE - OVERLAP)

async def query_llm_async(model_name, system_prompt, user_prompt, enforce_json=False, api_key=""):
    """Phase 4 Helper: HYBRID ROUTER - Routes to Local Ollama or Cloud API."""
    
    enhanced_system_prompt = (
        "You are an expert bilingual data-entry AI. Your ONLY job is to extract specific data from foreign text and translate it to English.\n\n"
        "RULES:\n"
        "1. Find the target field in the context. Be smart about acronyms (e.g., RUC = Registration ID).\n"
        "2. Translate its value to English.\n"
        "3. Output ONLY the value. NEVER write sentences or explanations.\n"
        "4. If it is not in the context, output exactly 'Not Found'."
    )


    # CLOUD API ROUTE (For OpenAI GPT Models):I could not find a free API Key, so in the other files, I have used Gemini
    if model_name.startswith("gpt-"):
        if not api_key:
            return "Error: API Key Required", 0.0
            
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        if enforce_json:
            enhanced_system_prompt += "\n\nYou MUST respond in valid JSON format like this: {\"extracted_value\": \"your answer\"}"
            
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": enhanced_system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0
        }
        
        if enforce_json:
            payload["response_format"] = {"type": "json_object"}
            
        start_time = time.time()
        try:
            response = await asyncio.to_thread(requests.post, url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            raw_content = response.json()['choices'][0]['message']['content']
            latency = round(time.time() - start_time, 2)
            
            if enforce_json:
                try:
                    parsed = json.loads(raw_content)
                    return str(parsed.get("extracted_value", "Not Found")).strip(), latency
                except:
                    return "Parse Error", latency
            return raw_content.strip(), latency
        except Exception as e:
            return f"API Error", round(time.time() - start_time, 2)


    # LOCAL ROUTE (For Ollama 14B/7B)
    else:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": enhanced_system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.0} 
        }

        if enforce_json:
            payload["format"] = {
               "type": "object",
               "properties": {"extracted_value": {"type": "string"}},
               "required": ["extracted_value"]
            }

        async with ollama_semaphore:
            start_time = time.time()
            try:
                response = await asyncio.to_thread(requests.post, "http://localhost:11434/api/chat", json=payload, timeout=90)
                response.raise_for_status()
                raw_content = response.json()['message']['content']
                latency = round(time.time() - start_time, 2)
                
                if enforce_json:
                    try:
                        parsed_json = json.loads(raw_content)
                        extracted_val = str(parsed_json.get("extracted_value", "Not Found")).strip()
               
                        words = extracted_val.split()
                        if len(words) > 15: extracted_val = " ".join(words[:15])
                        return extracted_val.replace('"', '').replace("'", ""), latency
                    except:
                        return "Not Found", latency
                return raw_content.strip(), latency
            except Exception as e:
                return "Timeout/Error", round(time.time() - start_time, 2)