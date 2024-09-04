import os
import boto3
import botocore
from main.utils.logger_utils import logger
from main.utils.custom_error_utils import S3Error
from PIL import Image


class S3Utils:
    def __init__(self):
        self.bucket_name = os.environ.get("S3_PUBLIC_BUCKET", "dhi-disclosures-public-dev")
        self.aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
        self.aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

    def fetch_pdf_from_s3(self, key):
        session = boto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

        s3 = session.client("s3")
        try:
            temp_pdf = key.split("/")[-1]
            s3.download_file(self.bucket_name, key, temp_pdf)
            return temp_pdf
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] == "404":
                logger.error("File not found in S3: %s", key)
                raise S3Error(f"File not found in S3: {key}")
            else:
                logger.exception("Error reading data from S3: %s", error)
            return None

    def fetch_logo_from_s3(self, asx_code):
        session = boto3.Session()

        s3 = session.client("s3")
        s3_logo_name = f"company_logo/{asx_code}.ico"
        temp_logo_file = f"output/{asx_code}.ico"
        converted_logo_file = f"output/{asx_code}.png"

        try:
            # Download the .ico file from S3
            s3.download_file(self.bucket_name, s3_logo_name, temp_logo_file)

            # Convert .ico file to .png using Pillow
            with Image.open(temp_logo_file) as img:
                img.save(converted_logo_file, format='PNG')

            # Remove the .ico file after conversion
            os.remove(temp_logo_file)

            return converted_logo_file
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] == "404":
                logger.warning(f"Logo not found in S3: {s3_logo_name}. Proceeding with no logo.")
                return None  # Return None if the logo is not found
            else:
                logger.exception("Error reading data from S3: %s", error)
                return None
        except Exception as e:
            logger.error(f"Error converting logo from .ico to .png: {e}")
            return None