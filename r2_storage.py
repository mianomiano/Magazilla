import boto3
from botocore.config import Config as BotoConfig
import os
import uuid
from config import Config

def get_r2_client():
    return boto3.client(
        's3',
        endpoint_url=f'https://{Config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=Config.R2_ACCESS_KEY,
        aws_secret_access_key=Config.R2_SECRET_KEY,
        config=BotoConfig(signature_version='s3v4'),
        region_name='auto'
    )

def upload_to_r2(file, folder='files'):
    """Upload file to R2 and return the key"""
    try:
        client = get_r2_client()
        
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        unique_name = f"{folder}/{uuid.uuid4().hex}.{ext}" if ext else f"{folder}/{uuid.uuid4().hex}"
        
        # Determine content type
        content_types = {
            'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'gif': 'image/gif', 'webp': 'image/webp', 'webm': 'video/webm',
            'mp4': 'video/mp4', 'svg': 'image/svg+xml', 'pdf': 'application/pdf',
            'zip': 'application/zip', 'psd': 'application/octet-stream',
            'ai': 'application/postscript', 'fig': 'application/octet-stream'
        }
        content_type = content_types.get(ext, 'application/octet-stream')
        
        # Upload
        client.upload_fileobj(
            file,
            Config.R2_BUCKET,
            unique_name,
            ExtraArgs={'ContentType': content_type}
        )
        
        return unique_name
    except Exception as e:
        print(f"R2 upload error: {e}")
        return None

def get_r2_url(key, expires=3600):
    """Get presigned URL for downloading"""
    if not key:
        return None
    try:
        # If custom public URL is set, use it
        if Config.R2_PUBLIC_URL:
            return f"{Config.R2_PUBLIC_URL}/{key}"
        
        client = get_r2_client()
        url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': Config.R2_BUCKET, 'Key': key},
            ExpiresIn=expires
        )
        return url
    except Exception as e:
        print(f"R2 URL error: {e}")
        return None

def delete_from_r2(key):
    """Delete file from R2"""
    if not key:
        return False
    try:
        client = get_r2_client()
        client.delete_object(Bucket=Config.R2_BUCKET, Key=key)
        return True
    except Exception as e:
        print(f"R2 delete error: {e}")
        return False
