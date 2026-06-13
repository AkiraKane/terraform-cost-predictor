# Terraform Cost Predictor (Day 23)

Estimate monthly cloud costs from Terraform plans using pricing data and AI-powered explanations.

## Features

- Parses Terraform plan JSON (`terraform show -json plan`)
- Estimates costs for 30+ common AWS, GCP, and Azure resource types
- Supports EC2, RDS, S3, Lambda, DynamoDB, EKS, ELB, and more
- AI-powered cost analysis via Ollama (local) or OpenAI (fallback)
- JSON and human-readable output formats
- Highlights top expensive resources and cost by type

## Requirements

- Python 3.11+
- Terraform (to generate plan files)
- Ollama (optional, for local AI) or OpenAI API key (optional, for remote AI)

## Quick Start

```bash
# Generate a Terraform plan JSON
cd your-terraform-project
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json

# Run cost estimation
python src/main.py plan.json

# With AI explanation
python src/main.py plan.json --explain

# JSON output
python src/main.py plan.json --json
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Ollama model name |
| `OPENAI_API_KEY` | (none) | OpenAI API key for fallback |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model name |

## Architecture

```
terraform-cost-predictor/
  src/
    cost_estimator.py   # Core cost estimation logic + pricing data
    llm.py              # LLM client (Ollama + OpenAI fallback)
    main.py             # CLI entry point
  tests/
    test_cost_estimator.py  # Comprehensive test suite
  .github/workflows/
    ci.yml              # GitHub Actions CI
  Dockerfile
  docker-compose.yml
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Docker

```bash
# Build and run
docker compose run terraform-cost-predictor /app/plans/plan.json

# Or with AI explanation
docker compose run terraform-cost-predictor /app/plans/plan.json --explain
```
