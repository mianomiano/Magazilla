"""Cloudflare R2 storage utilities"""
import boto3
from botocore.config import Config as BotoConfig
from config import Config


def get_r2_client():
    """Get configured R2 (S3-compatible) client"""
    if not all([Config.R2_ACCOUNT_ID, Config.R2_ACCESS_KEY, Config.R2_SECRET_KEY]):
        return None
    
    return boto3.client(
        's3',
        endpoint_url=f'https://{Config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=Config.R2_ACCESS_KEY,
        aws_secret_access_key=Config.R2_SECRET_KEY,
        config=BotoConfig(signature_version='s3v4')
    )


def get_r2_url(file_path: str, expires: int = 300) -> str:
    """
    Generate a presigned URL for downloading a file from R2.
    
    Args:
        file_path: The path/key of the file in R2 bucket
        expires: URL expiration time in seconds (default 5 minutes)
    
    Returns:
        Presigned URL string, or None if R2 is not configured
    """
    if not file_path:
        return None
    
    # If it's already a full URL, return as-is
    if file_path.startswith('http://') or file_path.startswith('https://'):
        return file_path
    
    # If R2 public URL is configured, use it for public files
    if Config.R2_PUBLIC_URL:
        return f"{Config.R2_PUBLIC_URL.rstrip('/')}/{file_path.lstrip('/')}"
    
    # Generate presigned URL
    client = get_r2_client()
    if not client:
        return None
    
    try:
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': Config.R2_BUCKET,
                'Key': file_path
            },
            ExpiresIn=expires
        )
        return url
    except Exception as e:
        print(f"Error generating R2 URL: {e}")
        return None


def upload_to_r2(file_data, file_path: str, content_type: str = None) -> bool:
    """
    Upload a file to R2 storage.
    
    Args:
        file_data: File data (bytes or file-like object)
        file_path: Destination path/key in R2 bucket
        content_type: MIME type of the file
    
    Returns:
        True if upload successful, False otherwise
    """
    client = get_r2_client()
    if not client:
        print("R2 client not configured")
        return False
    
    try:
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        
        client.put_object(
            Bucket=Config.R2_BUCKET,
            Key=file_path,
            Body=file_data,
            **extra_args
        )
        return True
    except Exception as e:
        print(f"Error uploading to R2: {e}")
        return False


def delete_from_r2(file_path: str) -> bool:
    """
    Delete a file from R2 storage.
    
    Args:
        file_path: Path/key of the file to delete
    
    Returns:
        True if deletion successful, False otherwise
    """
    client = get_r2_client()
    if not client:
        return False
    
    try:
        client.delete_object(
            Bucket=Config.R2_BUCKET,
            Key=file_path
        )
        return True
    except Exception as e:
        print(f"Error deleting from R2: {e}")
        return False
