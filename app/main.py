# This version would help you, run the code locally using Ollama models, having 16B parameters.
# The main.py and services.py files also are designed for API calls, but do not try  them out as they are unoptimized.

import os
import shutil
import json
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import openpyxl
import chromadb
from sentence_transformers import SentenceTransformer

from app.services import extract_text_from_pdf, query_llm_async

app = FastAPI(title="Multilingual Document-to-Excel RAG Core")

@app.get("/")
async def home():
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
        "index.html"
    )
    print("Serving:", path)
    return FileResponse(path)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "./chroma_db"
chroma_client = chromadb.PersistentClient(path=DB_PATH)

# The embedding_model has been used because of it higher throughput and lower RAM usage.

embedding_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

class ChatQuery(BaseModel):
    query: str
    model_selection: str = "qwen2.5:14b"
    api_key: str = ""

# Global variable to hold the Page 1 anchor, as page 1 is often not scanned and contains crucial details.
CURRENT_DOC_ANCHOR = ""

@app.post("/api/process")
async def process_document(
    doc_file: UploadFile = File(...), 
    excel_file: UploadFile = File(...),
    model_selection: str = Form("qwen2.5:14b"),
    api_key: str = Form("") 
):
    global CURRENT_DOC_ANCHOR
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    
    doc_path = f"uploads/{doc_file.filename}"
    excel_path = f"uploads/{excel_file.filename}"
    output_excel_path = f"output/filled_{excel_file.filename}"
    
    with open(doc_path, "wb") as buffer:
        shutil.copyfileobj(doc_file.file, buffer)
    with open(excel_path, "wb") as buffer:
        shutil.copyfileobj(excel_file.file, buffer)

    async def event_stream():
        global CURRENT_DOC_ANCHOR
        try:
            yield json.dumps({"status": "log", "message": "Phase 1/4: Running OCR & Smart Chunking..."}) + "\n"
            extracted_chunks = await asyncio.to_thread(extract_text_from_pdf, doc_path)
            
            if not extracted_chunks:
                yield json.dumps({"status": "error", "message": "No readable text found."}) + "\n"
                return

            # Capturing a massive 3000 character anchor
            page_1_text = "\n".join([c["text"] for c in extracted_chunks if c["page"] == 1])
            CURRENT_DOC_ANCHOR = page_1_text[:3000] 

            yield json.dumps({"status": "log", "message": "Phase 2/4: Vectorizing text into ChromaDB..."}) + "\n"
            try: chroma_client.delete_collection("client_doc")
            except Exception: pass
            
            collection = chroma_client.create_collection("client_doc")
            texts = [c["text"] for c in extracted_chunks]
            metadatas = [{"page": c["page"]} for c in extracted_chunks]
            ids = [f"chunk_{i}" for i in range(len(extracted_chunks))]
            
            vectors = await asyncio.to_thread(embedding_model.encode, texts)
            collection.add(embeddings=vectors.tolist(), documents=texts, metadatas=metadatas, ids=ids)

            yield json.dumps({"status": "log", "message": "Phase 3/4: Creating Parallel Tasks..."}) + "\n"
            wb = openpyxl.load_workbook(excel_path)
            
            retrieval_cache = {}
            tasks = []

            async def process_column_task(sheet_name, col_idx, header):
                if header not in retrieval_cache:
                    q_vector = await asyncio.to_thread(embedding_model.encode, str(header))
                    search_results = await asyncio.to_thread(collection.query, query_embeddings=[q_vector.tolist()], n_results=4)
                    retrieval_cache[header] = search_results
                
                search_results = retrieval_cache[header]
                retrieved_str = "\n".join(search_results['documents'][0]) if search_results['documents'] else ""
                pages_found = list(set([meta['page'] for meta in search_results['metadatas'][0]])) if search_results['metadatas'] else []
                
                context_str = f"--- CORE DOCUMENT INFO (PAGE 1) ---\n{CURRENT_DOC_ANCHOR}\n\n--- ADDITIONAL SEARCH RESULTS ---\n{retrieved_str}"
                
                system_prompt = "Extract the requested target field from the context. Translate the value to English."
                user_prompt = f"Target Field: {header}\n\nContext:\n{context_str}"
                
                # Passes the API key variable down to the routing engine
                extracted_val, latency = await query_llm_async(model_selection, system_prompt, user_prompt, True, api_key)
                
                if 1 not in pages_found: pages_found.insert(0, 1)

                return {
                    "sheet_name": sheet_name, "col_idx": col_idx, "header": header,
                    "val": extracted_val, "pages": pages_found, "latency": latency
                }

            for sheet in wb.worksheets:
                sheet_name = sheet.title
                headers = [cell.value for cell in sheet[1] if cell.value is not None]
                for col_idx, header in enumerate(headers, start=1):
                    tasks.append(process_column_task(sheet_name, col_idx, header))

            total_columns = len(tasks)
            processed_columns = 0
            yield json.dumps({"status": "log", "message": f"Phase 4/4: Executing {total_columns} agents..."}) + "\n"

            for coro in asyncio.as_completed(tasks):
                result = await coro
                processed_columns += 1
                
                sheet = wb[result["sheet_name"]]
                sheet.cell(row=2, column=result["col_idx"], value=result["val"])
                
                yield json.dumps({
                    "status": "extracted", "current": processed_columns, "total": total_columns,
                    "sheet": result["sheet_name"], "column": result["header"],
                    "value": result["val"], "pages": result["pages"], "latency": result["latency"]
                }) + "\n"
                    
            wb.save(output_excel_path)
            yield json.dumps({"status": "done", "file_path": output_excel_path}) + "\n"
            
        except Exception as e:
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@app.post("/api/chat")
async def interactive_chat(payload: ChatQuery):
    global CURRENT_DOC_ANCHOR
    try:
        collection = chroma_client.get_collection("client_doc")
        query_vector = embedding_model.encode(payload.query).tolist()
        search_results = collection.query(query_embeddings=[query_vector], n_results=4)
        
        retrieved_str = "\n".join(search_results['documents'][0]) if search_results and search_results['documents'] else ""
        citations = [meta['page'] for meta in search_results['metadatas'][0]] if search_results and search_results['metadatas'] else []
        if 1 not in citations: citations.insert(0, 1)

        context_str = f"--- CORE DOCUMENT INFO (PAGE 1) ---\n{CURRENT_DOC_ANCHOR}\n\n--- ADDITIONAL SEARCH RESULTS ---\n{retrieved_str}"
            
        system_prompt = "You are a bilingual document support assistant. Answer queries concisely in English using the provided context."
        user_prompt = f"Query: {payload.query}\n\nDocument Context:\n{context_str}"
        
        # Passes the selected model and API key for the Chat interface too
        ai_response, _ = await query_llm_async(payload.model_selection, system_prompt, user_prompt, False, payload.api_key)
        
        return {"response": ai_response, "citations_pages": list(set(citations))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download")
async def download_file(path: str):
    if os.path.exists(path):
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=os.path.basename(path))
    raise HTTPException(status_code=404, detail="Requested file resource not found.")