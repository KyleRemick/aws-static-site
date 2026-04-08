# aws-static-site

## Summary
Small Python project that uploads a static page to S3 and serves it through CloudFront.

## AWS services used
- Amazon S3
- Amazon CloudFront

## How to deploy
1. Set AWS credentials and default region in your environment or AWS config.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Run:
   `python deploy.py`

The script prints the CloudFront URL and saves a local `deployment.json` file for cleanup.

## How to clean up
Run:
`python cleanup.py`

## Architecture
`website/index.html` is uploaded to a new S3 bucket. A CloudFront distribution is created with the bucket as the origin, and the URL is returned.
