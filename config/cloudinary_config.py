import cloudinary
import os
import cloudinary.uploader

cloudinary.config(
    cloud_name = os.getenv("CLOUD_NAME"),
    api_key = os.getenv("CLOUD_KEY"),
    api_secret = os.getenv("CLOUD_SECRET"),
    secure = True
)