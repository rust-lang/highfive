# Introduction
This directory contains files used to provision Highfive EC2 instances
and deploy Highfive onto them. A provisioned machine can be deployed
to repeatedly.

# Provisioning
## First-time Setup in AWS
If you haven't provisioned a Highfive instance previously, you need to
set up an IAM role, KMS key, and a security group. You may also need
to set up a VPC and subnet, if you don't already have them configured
in your AWS account. There is no Highfive-specific configuration for
the VPC and subnet, so configuration for them is not described
further. Details for the other components are below.

1. Create an IAM role for the Highfive instance. The rest of this
document will assume the role is called "highfive". We will represent
the role's ARN as `IAM_ROLE_ARN` below.
1. Create a KMS key. Let's call this `KMS_KEY_ID`. Make the highfive
role a user of this key.
1. Create a security group. Let's call this `SEC_GROUP_ID`. At a
minimum, grant inbound access to TCP ports 22 and 80, and grant
inbound access to UCP ports 60000-61000, if you want to be able to
connect with [Mosh](https://mosh.org/).
1. Create or get the ID of your VPC subnet. Let's call this
`VPC_SUBNET_ID`.

If you find yourself needing to run a command that begins with `aws`
below (i.e., provisioning and instance or changing Highfive's config
file), you will need to have the [AWS
CLI](https://aws.amazon.com/cli/) set up and have AWS tokens that
grant you the necessary permissions.

## Creating the config.secure File
The config.secure file contains the encrypted contents of the config
file that Highfive uses. If one does not exist or you need to change
it, use the command below on your plaintext config file.

```
$ aws kms encrypt --key-id KMS_KEY_ID --plaintext fileb://config --output text --query CiphertextBlob | base64 --decode > config.secure
```

The config.secure file needs to be checked in, but do not check in the
plaintext file.

## Provisioning and Setting Up an Instance
The following command provisions an EC2 instance, sets it up, and
deploys the current Highive master branch onto it. You will generally
want to run this command if there is not an existing Highfive instance
or you are replacing an old one.

```
$ aws ec2 run-instances --region us-east-1 --image-id ami-5cc39523 --count 1 --instance-type t2.micro --iam-instance-profile Arn=IAM_ROLE_ARN --subnet-id VPC_SUBNET_ID --security-group-ids SEC_GROUP_ID --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=highfive}]' --associate-public-ip-address --user-data file://instance-init
```

For example, my command to do this is the following.
```
$ aws --profile personal ec2 run-instances --region us-east-1 --image-id ami-5cc39523 --count 1 --instance-type t2.micro --iam-instance-profile Arn=arn:aws:iam::462876742192:instance-profile/highfive --subnet-id subnet-c654bc9d --security-group-ids sg-04f40c66422354223 --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=highfive}]' --associate-public-ip-address --user-data file://instance-init
```

# Deploying
To deploy to an existing instance, you need to have ssh access. To
deploy the master branch do the following:

```
$ ssh ubuntu@HIGHFIVE-HOST ./deploy master
```

The last line of the output will indicate if deployment was
successful.

The deployment script accepts any Git target. For example, you can
provide commit hashes, branch names, and tags. An example
demonstrating deployment of a specific commit hash is below.

```
$ ssh ubuntu@HIGHFIVE-HOST ./deploy 225df77
```
