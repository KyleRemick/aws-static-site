import json
import time
import uuid
from pathlib import Path

import boto3

PROJECT_ROOT = Path(__file__).parent
WEBSITE_DIR = PROJECT_ROOT / "website"
INDEX_FILE = WEBSITE_DIR / "index.html"
STATE_FILE = PROJECT_ROOT / "deployment.json"


def make_bucket_name():
    suffix = uuid.uuid4().hex[:10]
    return f"aws-static-site-{suffix}"


def create_bucket(s3_client, region, bucket_name):
    if region == "us-east-1":
        s3_client.create_bucket(Bucket=bucket_name)
    else:
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region},
        )


def configure_public_bucket(s3_client, bucket_name):
    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": False,
            "IgnorePublicAcls": False,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": False,
        },
    )

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadForStaticSite",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
            }
        ],
    }
    s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))


def upload_index(s3_client, bucket_name):
    s3_client.upload_file(
        str(INDEX_FILE),
        bucket_name,
        "index.html",
        ExtraArgs={"ContentType": "text/html"},
    )


def create_distribution(cloudfront_client, bucket_name, region):
    if region == "us-east-1":
        origin_domain = f"{bucket_name}.s3.amazonaws.com"
    else:
        origin_domain = f"{bucket_name}.s3.{region}.amazonaws.com"

    origin_id = f"s3-{bucket_name}"
    response = cloudfront_client.create_distribution(
        DistributionConfig={
            "CallerReference": str(time.time()),
            "Comment": "Static site distribution",
            "Enabled": True,
            "DefaultRootObject": "index.html",
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": origin_id,
                        "DomainName": origin_domain,
                        "S3OriginConfig": {"OriginAccessIdentity": ""},
                    }
                ],
            },
            "DefaultCacheBehavior": {
                "TargetOriginId": origin_id,
                "ViewerProtocolPolicy": "redirect-to-https",
                "AllowedMethods": {
                    "Quantity": 2,
                    "Items": ["GET", "HEAD"],
                    "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
                },
                "ForwardedValues": {
                    "QueryString": False,
                    "Cookies": {"Forward": "none"},
                },
                "MinTTL": 0,
            },
            "PriceClass": "PriceClass_100",
        }
    )
    distribution = response["Distribution"]
    return distribution["Id"], distribution["DomainName"]


def main():
    if not INDEX_FILE.exists():
        raise FileNotFoundError(f"Missing {INDEX_FILE}")

    session = boto3.session.Session()
    region = session.region_name or "us-east-1"
    s3 = session.client("s3", region_name=region)
    cloudfront = session.client("cloudfront")

    bucket_name = make_bucket_name()
    create_bucket(s3, region, bucket_name)
    configure_public_bucket(s3, bucket_name)
    upload_index(s3, bucket_name)
    distribution_id, distribution_domain = create_distribution(
        cloudfront, bucket_name, region
    )

    state = {
        "bucket_name": bucket_name,
        "region": region,
        "distribution_id": distribution_id,
        "distribution_domain": distribution_domain,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))

    print(f"CloudFront URL: https://{distribution_domain}")
    print(f"State saved to: {STATE_FILE}")


if __name__ == "__main__":
    main()
