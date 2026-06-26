# Installations

This would allow the processing of documents in all of the following languages: Spanish, English, Arabic, Malay, Italian, Chinese

For using this, the following downloads are necessary: (They can be done using Command Prompt)

1. Python 3.13 and above Link (https://www.python.org/)

2. Tesseract-OCR (Link: https://tesseract-ocr.github.io/tessdoc/Downloads.html)

3. Poppler (Link: https://github.com/oschwartz10612/poppler-windows)

   These should be added to path by going to System properties -> Advanced -> Environmental Variables -> User Variables -> Path -> Add New and paste the location of the file

4. Ollama (Link: https://ollama.com/search)

I have focused my implementation on the Qwen 2.5 family of models for your local processing requirements.

Here is the breakdown of the specific models we have utilized in the setup:

1. qwen2.5:14b (14 billion parameters) ->  I have configured this as your primary high-performance local engine, noting that it requires at least 16GB of RAM to run effectively.

2. mistral:7b (7 billion parameters)
           
3. qwen2.5:7b (7 billion parameters)    -> I configured this as your fallback local engine, designed to run within the tighter constraints of an 8GB RAM machine.
   
4. llama3:8b (8 billion parameters)    
