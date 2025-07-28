# StateCraft

![GitHub License](https://img.shields.io/github/license/devopsgroupeu/StateCraft)

[![LinkedIn](https://img.shields.io/badge/linkedin-%230077B5.svg?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/devopsgroup8/)

Manage AWS resources (S3 Bucket and optional DynamoDB Table) for Terraform backend state.

## Prerequisites

### AWS Credentials

Don't forget to configure credentials to your AWS account. Learn more [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html).

##  Examples

### S3 locking mechanisim

> For Terraform version 1.9.0 or greater.

```sh
py src/main.py create \
    --region eu-west-1 \
    --bucket-name my-terraform-bucket \
    --locking-mechanism s3
```

### DynamoDB locking mechanisim
```sh
py src/main.py create \
    --region eu-west-1 \
    --bucket-name my-terraform-bucket \
    --table_name my-terraform-locking \
    --locking-mechanism dynamodb
```

## License

```
Copyright 2025 DevOpsGroup

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```