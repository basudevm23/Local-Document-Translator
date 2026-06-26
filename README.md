**Setup**

Once all the installations mentioned in Installations.md are complete, proceed with the following:

1. Download all files by cloning this git repository or directly download as a zip file.

2. Create a virtual environment by going to cmd prompt (open it by going to the location where the files are downloaded).
   
   Use the following commands: python -m venv abcd (abcd is the name of the virtual env), followed by abcd/Scripts/activate

4. Once you are in the virtual environment: pip install -r reqfile.txt

5. Type the following command, it will redirect you to the interface: uvicorn app.main:app --reload --port 8000


<img width="1742" height="1023" alt="image" src="https://github.com/user-attachments/assets/a7ea4072-94f0-42e6-ad10-48a19780c21b" />

<img width="1557" height="1037" alt="image" src="https://github.com/user-attachments/assets/6300aaa2-c763-40b2-955a-f0aff1afab20" />

Now upload all files and start processing. Create a new excel file with only the fields mentioned as column and upload it.  After processing, the tool will automatically fill them.

The following is how it will look after processing, it will also lead you to download the filled up excel file. (The names visible in the frontend have been modified). 

<img width="1027" height="422" alt="image" src="https://github.com/user-attachments/assets/226d34e2-aadb-4657-aae2-1a2fc811f88b" />

<img width="1918" height="365" alt="image" src="https://github.com/user-attachments/assets/379c4ecc-441a-494f-91ec-75e8c1258359" />



