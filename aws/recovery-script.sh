#!/bin/bash
#
# Power Management System - Deployment Recovery Script
# This script helps recover from failed deployment and redeploy successfully
#
# Usage: Run each section step-by-step, not all at once
#

set -e

REGION="us-west-2"
STACK_NAME="powermgr-prod"
USER_NAME="powermgr-lambda-user"

echo "============================================"
echo "Power Management Deployment Recovery Script"
echo "============================================"
echo ""
echo "⚠️  IMPORTANT: Run this step-by-step, not all at once!"
echo "   Read each section and verify before proceeding"
echo ""

# ============================================
# STEP 1: Add IAM Permissions
# ============================================
echo "STEP 1: Add IAM Permissions"
echo "----------------------------"
echo ""
echo "Run these commands to attach necessary IAM policies:"
echo ""
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/AWSCloudFormationFullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/IAMFullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess"
echo "aws iam attach-user-policy --user-name $USER_NAME --policy-arn arn:aws:iam::aws:policy/AmazonSSMFullAccess"
echo ""
read -p "Press Enter after you've added permissions via Console or run the commands above..."

# ============================================
# STEP 2: Verify Permissions
# ============================================
echo ""
echo "STEP 2: Verify Permissions"
echo "--------------------------"
echo ""
aws iam list-attached-user-policies --user-name $USER_NAME
echo ""
read -p "Verify policies are attached above. Press Enter to continue..."

# ============================================
# STEP 3: Clean Up Failed Resources
# ============================================
echo ""
echo "STEP 3: Clean Up Failed Resources"
echo "----------------------------------"
echo ""

# Delete orphaned log groups
echo "Deleting orphaned CloudWatch log groups..."
LOG_GROUPS=(
    "/aws/lambda/PowerMgr-DataCollector-prod"
    "/aws/lambda/PowerMgr-Analytics-prod"
    "/aws/lambda/PowerMgr-ThermostatController-prod"
    "/aws/lambda/PowerMgr-PeakManager-prod"
    "/aws/lambda/PowerMgr-PrecoolCheck-prod"
    "/aws/lambda/PowerMgr-EODStatus-prod"
    "/aws/lambda/PowerMgr-AuthRefresh-prod"
    "/aws/lambda/PowerMgr-WeeklyReport-prod"
)

for log_group in "${LOG_GROUPS[@]}"; do
    echo "Checking $log_group..."
    if aws logs describe-log-groups --log-group-name-prefix "$log_group" --region $REGION 2>/dev/null | grep -q "$log_group"; then
        echo "  Deleting $log_group..."
        aws logs delete-log-group --log-group-name "$log_group" --region $REGION || echo "  Already deleted or doesn't exist"
    else
        echo "  Doesn't exist, skipping"
    fi
done

echo ""
echo "Deleting failed CloudFormation stack..."
aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION

echo ""
echo "Waiting for stack deletion to complete (this may take 1-2 minutes)..."
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $REGION 2>/dev/null || echo "Stack deletion complete or stack doesn't exist"

echo ""
echo "Verifying stack is deleted..."
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION 2>&1 | grep -q "does not exist"; then
    echo "✓ Stack successfully deleted"
else
    echo "⚠️  Stack might still exist. Check manually:"
    aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION
fi

echo ""
read -p "Press Enter to continue to deployment..."

# ============================================
# STEP 4: Build and Deploy
# ============================================
echo ""
echo "STEP 4: Build and Deploy"
echo "------------------------"
echo ""

echo "Building SAM application with container..."
sam build --use-container

echo ""
echo "Starting guided deployment..."
echo ""
echo "Use these values when prompted:"
echo "  Stack Name: powermgr-prod"
echo "  AWS Region: us-west-2"
echo "  Parameter Environment: prod"
echo "  Confirm changes: Y"
echo "  Allow IAM role creation: Y"
echo "  Disable rollback: N"
echo "  Save to config file: Y"
echo ""
read -p "Press Enter to start sam deploy --guided..."

sam deploy --guided

echo ""
echo "✓ Deployment complete!"
echo ""

# ============================================
# STEP 5: Post-Deployment Configuration
# ============================================
echo ""
echo "STEP 5: Post-Deployment Configuration"
echo "--------------------------------------"
echo ""

read -p "Do you want to configure parameters now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Setting up default parameters..."
    make setup-params

    echo ""
    echo "Enabling dry-run mode for safe testing..."
    aws ssm put-parameter \
        --name /powermgr/config/dry_run \
        --value "true" \
        --type String \
        --region $REGION

    echo ""
    echo "✓ Basic configuration complete"
    echo ""
    echo "Next steps:"
    echo "1. Add your API credentials (see DEPLOYMENT_RECOVERY.md Step 6)"
    echo "2. Subscribe to SNS email notifications"
    echo "3. Test functions in dry-run mode"
    echo ""
fi

# ============================================
# Summary
# ============================================
echo ""
echo "============================================"
echo "Deployment Recovery Complete!"
echo "============================================"
echo ""
echo "Next Steps:"
echo "1. Add API credentials to Parameter Store (see DEPLOYMENT_RECOVERY.md)"
echo "2. Subscribe to email notifications"
echo "3. Test all functions: make invoke-collector, make invoke-analytics, etc."
echo "4. Monitor logs in dry-run mode for 24-48 hours"
echo "5. Disable dry-run when ready to go live"
echo ""
echo "See DEPLOYMENT_RECOVERY.md for detailed instructions"
echo ""
