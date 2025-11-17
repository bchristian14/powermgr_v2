.PHONY: help build deploy deploy-guided test clean validate setup-params init-token verify logs tail invoke report export-json export-csv

help:
	@echo "Power Management System - AWS Deployment (Forever Free)"
	@echo ""
	@echo "Available targets:"
	@echo "  build          - Build SAM application"
	@echo "  deploy         - Deploy to AWS (uses samconfig.toml)"
	@echo "  deploy-guided  - Deploy with guided prompts"
	@echo "  setup-params   - Setup Parameter Store configuration"
	@echo "  init-token     - Initialize Tesla token in DynamoDB"
	@echo "  verify         - Verify Parameter Store configuration"
	@echo "  test           - Run unit tests"
	@echo "  validate       - Validate SAM template"
	@echo "  invoke         - Manually invoke DataCollector function"
	@echo "  invoke-analytics - Manually invoke Analytics function"
	@echo "  logs           - View recent DataCollector logs"
	@echo "  logs-analytics - View recent Analytics logs"
	@echo "  tail           - Tail DataCollector logs in real-time"
	@echo "  tail-analytics - Tail Analytics logs in real-time"
	@echo "  report         - Generate weekly analytics report"
	@echo "  export-json    - Export metrics to JSON (requires START= END= FILE=)"
	@echo "  export-csv     - Export metrics to CSV (requires START= END= FILE=)"
	@echo "  clean          - Clean build artifacts"

build:
	sam build

deploy: build
	sam deploy

deploy-guided: build
	sam deploy --guided

deploy-dev: build
	sam deploy --config-env dev

validate:
	sam validate

setup-params:
	python3 scripts/setup_parameters.py --setup-all

init-token:
	@echo "Usage: make init-token TOKEN_FILE=../tesla.token"
	@if [ -z "$(TOKEN_FILE)" ]; then \
		echo "ERROR: TOKEN_FILE not specified"; \
		exit 1; \
	fi
	python3 scripts/init_tesla_token.py $(TOKEN_FILE) --verify

verify:
	python3 scripts/setup_parameters.py --verify

invoke:
	aws lambda invoke \
		--function-name PowerMgr-DataCollector-prod \
		--log-type Tail \
		response.json
	@cat response.json | python3 -m json.tool

invoke-analytics:
	aws lambda invoke \
		--function-name PowerMgr-Analytics-prod \
		--log-type Tail \
		response.json
	@cat response.json | python3 -m json.tool

logs:
	aws logs tail /aws/lambda/PowerMgr-DataCollector-prod --since 2h

logs-analytics:
	aws logs tail /aws/lambda/PowerMgr-Analytics-prod --since 2h

tail:
	aws logs tail /aws/lambda/PowerMgr-DataCollector-prod --follow

tail-analytics:
	aws logs tail /aws/lambda/PowerMgr-Analytics-prod --follow

test:
	pytest tests/ -v

clean:
	rm -rf .aws-sam/
	rm -f response.json
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# DynamoDB operations
check-metrics:
	aws dynamodb scan \
		--table-name PowerMetrics-prod \
		--select COUNT

check-state:
	aws dynamodb scan \
		--table-name PowerState-prod \
		--select COUNT

# Analytics and reporting
report:
	python3 scripts/analyze_metrics.py --report --days 7

export-json:
	@if [ -z "$(START)" ] || [ -z "$(END)" ] || [ -z "$(FILE)" ]; then \
		echo "Usage: make export-json START=2025-11-01 END=2025-11-30 FILE=data.json"; \
		exit 1; \
	fi
	python3 scripts/analyze_metrics.py --export-json $(FILE) --start-date $(START) --end-date $(END)

export-csv:
	@if [ -z "$(START)" ] || [ -z "$(END)" ] || [ -z "$(FILE)" ]; then \
		echo "Usage: make export-csv START=2025-11-01 END=2025-11-30 FILE=data.csv"; \
		exit 1; \
	fi
	python3 scripts/analyze_metrics.py --export-csv $(FILE) --start-date $(START) --end-date $(END)

# CloudWatch metrics
lambda-stats:
	aws cloudwatch get-metric-statistics \
		--namespace AWS/Lambda \
		--metric-name Invocations \
		--dimensions Name=FunctionName,Value=PowerMgr-DataCollector-prod \
		--start-time $$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
		--end-time $$(date -u +%Y-%m-%dT%H:%M:%S) \
		--period 3600 \
		--statistics Sum

# Stack operations
stack-status:
	aws cloudformation describe-stacks \
		--stack-name powermgr-prod \
		--query 'Stacks[0].StackStatus' \
		--output text

stack-outputs:
	aws cloudformation describe-stacks \
		--stack-name powermgr-prod \
		--query 'Stacks[0].Outputs' \
		--output table

delete-stack:
	@echo "WARNING: This will delete all resources!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		aws cloudformation delete-stack --stack-name powermgr-prod; \
		echo "Stack deletion initiated. Monitor with: make stack-status"; \
	fi
