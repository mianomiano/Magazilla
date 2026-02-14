import boto3
from botocore.config import Config as BotoConfig
from config import Config
import uuid
import os
import mimetypes

class R2Storage:
    def __init__(self):
        self.client = boto3.client(
            's3',
            endpoint_url=f'https://{Config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=Config.R2_ACCESS_KEY,
            aws_secret_access_key=Config.R2_SECRET_KEY,
            config=BotoConfig(
                signature_version='s3v4',
                region_name='auto'
            )
        )
        self.bucket = Config.R2_BUCKET
        self.public_url = Config.R2_PUBLIC_URL
    
    def upload_file(self, file_obj, folder='uploads'):
        """
        Upload a file to R2.
        Returns the public URL of the uploaded file.
        """
        # Get original extension
        original_filename = file_obj.filename if hasattr(file_obj, 'filename') else 'file'
        ext = os.path.splitext(original_filename)[1].lower()
        
        # Generate unique filename
        unique_name = f"{folder}/{uuid.uuid4().hex}{ext}"
        
        # Determine content type
        content_type = mimetypes.guess_type(original_filename)[0]
        if ext == '.webm':
            content_type = 'video/webm'
        elif not content_type:
            content_type = 'application/octet-stream'
        
        # Upload
        self.client.upload_fileobj(
            file_obj,
            self.bucket,
            unique_name,
            ExtraArgs={
                'ContentType': content_type,
            }
        )
        
        # Return public URL
        return f"{self.public_url}/{unique_name}"
    
    def upload_from_bytes(self, data, filename, folder='uploads'):
        """
        Upload raw bytes to R2.
        Returns the public URL.
        """
        ext = os.path.splitext(filename)[1].lower()
        unique_name = f"{folder}/{uuid.uuid4().hex}{ext}"
        
        content_type = mimetypes.guess_type(filename)[0]
        if ext == '.webm':
            content_type = 'video/webm'
        elif not content_type:
            content_type = 'application/octet-stream'
        
        self.client.put_object(
            Bucket=self.bucket,
            Key=unique_name,
            Body=data,
            ContentType=content_type,
        )
        
        return f"{self.public_url}/{unique_name}"
    
    def delete_file(self, file_url):
        """
        Delete a file from R2 by its public URL.
        """
        if not file_url or self.public_url not in file_url:
            return False
        
        # Extract key from URL
        key = file_url.replace(f"{self.public_url}/", "")
        
        try:
            self.client.delete_object(
                Bucket=self.bucket,
                Key=key
            )
            return True
        except Exception as e:
            print(f"Error deleting {key}: {e}")
            return False
    
    def list_files(self, folder='uploads', max_keys=100):
        """
        List files in a folder.
        """
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=f"{folder}/",
                MaxKeys=max_keys
            )
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'url': f"{self.public_url}/{obj['Key']}",
                    'size': obj['Size'],
                    'modified': obj['LastModified']
                })
            return files
        except Exception as e:
            print(f"Error listing files: {e}")
            return []


# Singleton instance
r2 = R2Storage()
