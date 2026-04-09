from fastapi import APIRouter, Form, UploadFile, File
import config

router = APIRouter()

@router.post("/upload")
async def upload_file(
    file_name: str = Form(...), 
    file: UploadFile = File(...)):
    file_content = await file.read()
    print("file content: ", file_content)
    try:
        result = config.cloud_client.uploader.upload(
            file_content,
            folder="sql_schemas"
        )
        print("content: ", result)
        return result
    except Exception as e:
        print(e)
