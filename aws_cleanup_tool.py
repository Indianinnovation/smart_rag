import boto3
import json
from datetime import datetime
import os

class AWSCleanupTool:
    def __init__(self, region='us-east-1'):
        self.region = region
        self.backup_dir = f"aws_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.backup_dir, exist_ok=True)
        
    def get_cost_estimate(self):
        """Get current month's cost"""
        try:
            ce = boto3.client('ce', region_name='us-east-1')
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            
            response = ce.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost']
            )
            
            cost = float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
            print(f"\n💰 Current Month Cost: ${cost:.2f}")
            
            if cost > 5:
                print(f"⚠️  WARNING: Already over $5 budget! Current: ${cost:.2f}")
            else:
                print(f"✅ Under budget. Remaining: ${5 - cost:.2f}")
            
            return cost
        except Exception as e:
            print(f"❌ Could not fetch cost data: {e}")
            return None
    
    def backup_s3_buckets(self):
        """List and backup S3 bucket metadata"""
        print("\n📦 Checking S3 Buckets...")
        s3 = boto3.client('s3')
        
        try:
            buckets = s3.list_buckets()['Buckets']
            backup_data = []
            
            for bucket in buckets:
                bucket_name = bucket['Name']
                print(f"  - {bucket_name}")
                
                bucket_info = {
                    'name': bucket_name,
                    'creation_date': str(bucket['CreationDate']),
                    'objects': []
                }
                
                try:
                    objects = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=100)
                    if 'Contents' in objects:
                        for obj in objects['Contents']:
                            bucket_info['objects'].append({
                                'key': obj['Key'],
                                'size': obj['Size'],
                                'last_modified': str(obj['LastModified'])
                            })
                except Exception as e:
                    bucket_info['error'] = str(e)
                
                backup_data.append(bucket_info)
            
            with open(f"{self.backup_dir}/s3_buckets.json", 'w') as f:
                json.dump(backup_data, f, indent=2)
            
            print(f"✅ S3 backup saved to {self.backup_dir}/s3_buckets.json")
            return backup_data
        except Exception as e:
            print(f"❌ Error backing up S3: {e}")
            return []
    
    def list_ec2_instances(self):
        """List EC2 instances"""
        print("\n🖥️  Checking EC2 Instances...")
        ec2 = boto3.client('ec2', region_name=self.region)
        
        try:
            instances = ec2.describe_instances()
            instance_data = []
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    state = instance['State']['Name']
                    instance_id = instance['InstanceId']
                    instance_type = instance['InstanceType']
                    
                    print(f"  - {instance_id} ({instance_type}) - {state}")
                    
                    instance_data.append({
                        'id': instance_id,
                        'type': instance_type,
                        'state': state,
                        'launch_time': str(instance.get('LaunchTime', ''))
                    })
            
            with open(f"{self.backup_dir}/ec2_instances.json", 'w') as f:
                json.dump(instance_data, f, indent=2)
            
            return instance_data
        except Exception as e:
            print(f"❌ Error listing EC2: {e}")
            return []
    
    def list_rds_databases(self):
        """List RDS databases"""
        print("\n🗄️  Checking RDS Databases...")
        rds = boto3.client('rds', region_name=self.region)
        
        try:
            databases = rds.describe_db_instances()
            db_data = []
            
            for db in databases['DBInstances']:
                db_id = db['DBInstanceIdentifier']
                status = db['DBInstanceStatus']
                engine = db['Engine']
                
                print(f"  - {db_id} ({engine}) - {status}")
                
                db_data.append({
                    'id': db_id,
                    'engine': engine,
                    'status': status,
                    'instance_class': db['DBInstanceClass']
                })
            
            with open(f"{self.backup_dir}/rds_databases.json", 'w') as f:
                json.dump(db_data, f, indent=2)
            
            return db_data
        except Exception as e:
            print(f"❌ Error listing RDS: {e}")
            return []
    
    def list_lambda_functions(self):
        """List Lambda functions"""
        print("\n⚡ Checking Lambda Functions...")
        lambda_client = boto3.client('lambda', region_name=self.region)
        
        try:
            functions = lambda_client.list_functions()
            func_data = []
            
            for func in functions['Functions']:
                func_name = func['FunctionName']
                runtime = func['Runtime']
                
                print(f"  - {func_name} ({runtime})")
                
                func_data.append({
                    'name': func_name,
                    'runtime': runtime,
                    'memory': func['MemorySize'],
                    'timeout': func['Timeout']
                })
            
            with open(f"{self.backup_dir}/lambda_functions.json", 'w') as f:
                json.dump(func_data, f, indent=2)
            
            return func_data
        except Exception as e:
            print(f"❌ Error listing Lambda: {e}")
            return []
    
    def list_dynamodb_tables(self):
        """List DynamoDB tables"""
        print("\n📊 Checking DynamoDB Tables...")
        dynamodb = boto3.client('dynamodb', region_name=self.region)
        
        try:
            tables = dynamodb.list_tables()
            table_data = []
            
            for table_name in tables['TableNames']:
                print(f"  - {table_name}")
                
                table_info = dynamodb.describe_table(TableName=table_name)
                table_data.append({
                    'name': table_name,
                    'status': table_info['Table']['TableStatus'],
                    'item_count': table_info['Table']['ItemCount']
                })
            
            with open(f"{self.backup_dir}/dynamodb_tables.json", 'w') as f:
                json.dump(table_data, f, indent=2)
            
            return table_data
        except Exception as e:
            print(f"❌ Error listing DynamoDB: {e}")
            return []
    
    def generate_cleanup_script(self):
        """Generate cleanup commands"""
        print("\n📝 Generating cleanup script...")
        
        script = """#!/bin/bash
# AWS Cleanup Script
# Generated on: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
# WARNING: Review carefully before running!

echo "Starting AWS cleanup..."

# Stop and terminate EC2 instances
# aws ec2 terminate-instances --instance-ids <instance-id>

# Delete S3 buckets (must be empty first)
# aws s3 rb s3://<bucket-name> --force

# Delete RDS databases
# aws rds delete-db-instance --db-instance-identifier <db-id> --skip-final-snapshot

# Delete Lambda functions
# aws lambda delete-function --function-name <function-name>

# Delete DynamoDB tables
# aws dynamodb delete-table --table-name <table-name>

echo "Cleanup complete!"
"""
        
        with open(f"{self.backup_dir}/cleanup_script.sh", 'w') as f:
            f.write(script)
        
        os.chmod(f"{self.backup_dir}/cleanup_script.sh", 0o755)
        print(f"✅ Cleanup script saved to {self.backup_dir}/cleanup_script.sh")
    
    def run_audit(self):
        """Run complete audit"""
        print("=" * 60)
        print("🔍 AWS ACCOUNT AUDIT & BACKUP TOOL")
        print("=" * 60)
        
        self.get_cost_estimate()
        self.backup_s3_buckets()
        self.list_ec2_instances()
        self.list_rds_databases()
        self.list_lambda_functions()
        self.list_dynamodb_tables()
        self.generate_cleanup_script()
        
        print("\n" + "=" * 60)
        print("✅ AUDIT COMPLETE!")
        print(f"📁 All backups saved to: {self.backup_dir}/")
        print("=" * 60)
        print("\n⚠️  NEXT STEPS:")
        print("1. Review the backup files")
        print("2. Download any important data from S3")
        print("3. Use AWS Console or CLI to delete resources")
        print("4. Check billing dashboard after cleanup")
        print("=" * 60)

if __name__ == "__main__":
    tool = AWSCleanupTool(region='us-east-1')
    tool.run_audit()
