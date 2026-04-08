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


def configure_private_bucket(s3_client, bucket_name):
    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )


def upload_index(s3_client, bucket_name):
    s3_client.upload_file(
        str(INDEX_FILE),
        bucket_name,
        "index.html",
        ExtraArgs={"ContentType": "text/html"},
    )


def create_origin_access_control(cloudfront_client, bucket_name):
    response = cloudfront_client.create_origin_access_control(
        OriginAccessControlConfig={
            "Name": f"{bucket_name}-oac",
            "Description": "Access control for private S3 origin",
            "SigningProtocol": "sigv4",
            "SigningBehavior": "always",
            "OriginAccessControlOriginType": "s3",
        }
    )
    return response["OriginAccessControl"]["Id"]


def create_distribution(cloudfront_client, bucket_name, region, oac_id):
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
                        "OriginAccessControlId": oac_id,
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


def apply_bucket_policy_for_cloudfront(s3_client, bucket_name, distribution_id, account_id):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowCloudFrontServicePrincipalReadOnly",
                "Effect": "Allow",
                "Principal": {"Service": "cloudfront.amazonaws.com"},
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
                "Condition": {
                    "StringEquals": {
                        "AWS:SourceArn": (
                            f"arn:aws:cloudfront::{account_id}:distribution/{distribution_id}"
                        )
                    }
                },
            }
        ],
    }
    s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))


def main():
    if not INDEX_FILE.exists():
        raise FileNotFoundError(f"Missing {INDEX_FILE}")

    session = boto3.session.Session()
    region = session.region_name or "us-east-1"
    s3 = session.client("s3", region_name=region)
    cloudfront = session.client("cloudfront")
    sts = session.client("sts")

    bucket_name = make_bucket_name()
    create_bucket(s3, region, bucket_name)
    configure_private_bucket(s3, bucket_name)
    upload_index(s3, bucket_name)
    oac_id = create_origin_access_control(cloudfront, bucket_name)
    distribution_id, distribution_domain = create_distribution(
        cloudfront, bucket_name, region, oac_id
    )
    account_id = sts.get_caller_identity()["Account"]
    apply_bucket_policy_for_cloudfront(s3, bucket_name, distribution_id, account_id)

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
