# StateCraft

```sh
py src/terraform_backend_manager.py create \
    --region $(yq .backend.s3.region ../../Packages/aws-premium/jinja/data/00_base.yaml) \
    --bucket-name $(yq .backend.s3.bucket ../../Packages/aws-premium/jinja/data/00_base.yaml) \
    --locking-mechanism s3
```