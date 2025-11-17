.PHONY: help build deploy deploy-guided test clean validate setup-params init-token verify logs tail invoke report export-json export-csv

help:
	@echo "Power Management System - AWS Deployment (Forever Free)"
	@echo ""
	@echo "Setup & Deployment:"
	@echo "  build          - Build SAM application"
	@echo "  deploy         - Deploy to AWS (uses samconfig.toml)"
	@echo "  deploy-guided  - Deploy with guided prompts"
	@echo "  setup-params   - Setup Parameter Store configuration"
	@echo "  init-token     - Initialize Tesla token in DynamoDB"
	@echo "  verify         - Verify Parameter Store configuration"
	@echo "  test           - Run unit tests"
	@echo "  validate       - Validate SAM template"
	@echo ""
	@echo "Phase 1 & 2 Functions (Data Collection & Analytics):"
	@echo "  invoke         - Manually invoke DataCollector"
	@echo "  invoke-analytics - Manually invoke Analytics"
	@echo "  logs           - View DataCollector logs"
	@echo "  logs-analytics - View Analytics logs"
	@echo ""
	@echo "Phase 3 Functions (Control & Management):"
	@echo "  invoke-thermostat - Invoke ThermostatController"
	@echo "  invoke-peak    - Invoke PeakManager"
	@echo "  invoke-precool - Invoke PrecoolCheck"
	@echo "  invoke-eod     - Invoke EODStatus"
	@echo "  invoke-auth    - Invoke AuthRefresh"
	@echo "  logs-thermostat - View ThermostatController logs"
	@echo "  logs-peak      - View PeakManager logs"
	@echo "  logs-precool   - View PrecoolCheck logs"
	@echo "  logs-eod       - View EODStatus logs"
	@echo "  logs-auth      - View AuthRefresh logs"
	@echo ""
	@echo "Analytics & Reporting:"
	@echo "  report         - Generate weekly analytics report"
	@echo "  export-json    - Export metrics to JSON (START= END= FILE=)"
	@echo "  export-csv     - Export metrics to CSV (START= END= FILE=)"
	@echo ""
	@echo "Utilities:"
	@echo "  clean          - Clean build artifacts"
	@echo "  stack-status   - Check CloudFormation stack status"
	@echo "  stack-outputs  - View stack outputs"

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

# Phase 3 Lambda functions
invoke-thermostat:
	aws lambda invoke \
		--function-name PowerMgr-ThermostatController-prod \
		--log-type Tail \
		response.json
	@cat response.json | python3 -m json.tool

invoke-peak:
	aws lambda invoke \
		--function-name PowerMgr-PeakManager-prod \
		--log-type Tail \
		response.json
	@cat response.json | python3 -m json.tool

invoke-precool:
	aws lambda invoke \
		--function-name PowerMgr-PrecoolCheck-prod \
		--log-type Tail \
		response.json
	@cat response.json | python3 -m json.tool

invoke-eod:
	aws lambda invoke \
		--function-name PowerMgr-EODStatus-prod \
		--log-type Tail \
		response.json
	@cat response.json | python3 -m json.tool

invoke-auth:
	aws lambda invoke \
		--function-name PowerMgr-AuthRefresh-prod \
		--log-type Tail \
		response.json
	@cat response.json | python3 -m json.tool

logs-thermostat:
	aws logs tail /aws/lambda/PowerMgr-ThermostatController-prod --since 2h

logs-peak:
	aws logs tail /aws/lambda/PowerMgr-PeakManager-prod --since 2h

logs-precool:
	aws logs tail /aws/lambda/PowerMgr-PrecoolCheck-prod --since 2h

logs-eod:
	aws logs tail /aws/lambda/PowerMgr-EODStatus-prod --since 2h

logs-auth:
	aws logs tail /aws/lambda/PowerMgr-AuthRefresh-prod --since 2h

tail-thermostat:
	aws logs tail /aws/lambda/PowerMgr-ThermostatController-prod --follow

tail-peak:
	aws logs tail /aws/lambda/PowerMgr-PeakManager-prod --follow

tail-precool:
	aws logs tail /aws/lambda/PowerMgr-PrecoolCheck-prod --follow

tail-eod:
	aws logs tail /aws/lambda/PowerMgr-EODStatus-prod --follow

tail-auth:
	aws logs tail /aws/lambda/PowerMgr-AuthRefresh-prod --follow

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
