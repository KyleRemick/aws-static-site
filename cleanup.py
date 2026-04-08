import json
from pathlib import Path

import boto3

PROJECT_ROOT = Path(__file__).parent
STATE_FILE = PROJECT_ROOT / "deployment.json"


def load_state():
    if not STATE_FILE.exists():
        raise FileNotFoundError(f"Missing {STATE_FILE}")
    return json.loads(STATE_FILE.read_text())


def disable_and_delete_distribution(cloudfront_client, distribution_id):
    config_response = cloudfront_client.get_distribution_config(Id=distribution_id)
    config = config_response["DistributionConfig"]
    etag = config_response["ETag"]

    if config.get("Enabled", True):
        config["Enabled"] = False
        update_response = cloudfront_client.update_distribution(
            Id=distribution_id, DistributionConfig=config, IfMatch=etag
        )
        etag = update_response["ETag"]

    waiter = cloudfront_client.get_waiter("distribution_deployed")
    waiter.wait(Id=distribution_id)

    config_response = cloudfront_client.get_distribution_config(Id=distribution_id)
    etag = config_response["ETag"]
    cloudfront_client.delete_distribution(Id=distribution_id, IfMatch=etag)


def delete_bucket_contents(s3_client, bucket_name):
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    contents = response.get("Contents", [])
    if not contents:
        return

    objects = [{"Key": obj["Key"]} for obj in contents]
    s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": objects})


def delete_bucket(s3_client, bucket_name):
    delete_bucket_contents(s3_client, bucket_name)
    s3_client.delete_bucket(Bucket=bucket_name)


def main():
    state = load_state()
    bucket_name = state["bucket_name"]
    region = state["region"]
    distribution_id = state["distribution_id"]

    session = boto3.session.Session()
    s3 = session.client("s3", region_name=region)
    cloudfront = session.client("cloudfront")

    disable_and_delete_distribution(cloudfront, distribution_id)
    delete_bucket(s3, bucket_name)

    STATE_FILE.unlink(missing_ok=True)
    print("Cleanup complete.")


if __name__ == "__main__":
    main()
