import asyncio
import os
import requests
import jwt
from datetime import datetime, timedelta

# Create a dummy small file
FILE_SIZE = 5 * 1024 * 1024 # 5 MB
FILE_NAME = "dummy_small.txt"
with open(FILE_NAME, "wb") as f:
    f.write(os.urandom(FILE_SIZE))

# Generate JWT
SECRET_KEY = "dev-only-insecure-secret-change-me"
ALGORITHM = "HS256"
user_id = 1
access_token_expires = timedelta(minutes=259200)
expire = datetime.utcnow() + access_token_expires
to_encode = {"sub": str(user_id), "exp": expire}
encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

headers = {
    "Authorization": f"Bearer {encoded_jwt}",
    "Content-Length": str(FILE_SIZE),
}

print("Uploading...")
with open(FILE_NAME, "rb") as f:
    response = requests.post(f"http://localhost:8000/api/upload/stream?filename={FILE_NAME}", data=f, headers=headers)

print(response.status_code, response.text)
if response.status_code == 200:
    res_data = response.json()
    msg_id = res_data.get("message_id")
    print(f"Uploaded! Msg ID: {msg_id}")
    
    # Complete upload to get file ID
    comp_data = {
        "filename": FILE_NAME,
        "file_size": FILE_SIZE,
        "mime_type": "text/plain",
        "message_ids": [msg_id]
    }
    comp_res = requests.post("http://localhost:8000/api/upload/complete", json=comp_data, headers={"Authorization": f"Bearer {encoded_jwt}"})
    print("Complete response:", comp_res.status_code, comp_res.text)
    
    file_record_id = comp_res.json()["id"]
    
    # Test download
    print(f"Downloading file {file_record_id}...")
    down_res = requests.get(f"http://localhost:8000/api/download/{file_record_id}", headers={"Authorization": f"Bearer {encoded_jwt}"}, stream=True)
    print("Download response status:", down_res.status_code)
    
    downloaded_size = 0
    for chunk in down_res.iter_content(chunk_size=1024*1024):
        if chunk:
            downloaded_size += len(chunk)
    
    print(f"Downloaded {downloaded_size} bytes. Expected: {FILE_SIZE}")
    if downloaded_size == FILE_SIZE:
        print("TEST PASSED")
    else:
        print("TEST FAILED")

os.remove(FILE_NAME)
