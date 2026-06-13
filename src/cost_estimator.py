"""Terraform cost estimator - analyzes plan JSON and estimates monthly costs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostEstimate:
    """Estimated monthly cost for a single resource."""

    resource_type: str
    resource_name: str
    monthly_cost: float
    currency: str = "USD"
    notes: str = ""

    @property
    def annual_cost(self) -> float:
        return self.monthly_cost * 12


@dataclass
class CostReport:
    """Aggregated cost report for a Terraform plan."""

    estimates: list[CostEstimate] = field(default_factory=list)
    currency: str = "USD"

    @property
    def total_monthly(self) -> float:
        return sum(e.monthly_cost for e in self.estimates)

    @property
    def total_annual(self) -> float:
        return self.total_monthly * 12

    @property
    def resource_count(self) -> int:
        return len(self.estimates)

    def by_type(self) -> dict[str, float]:
        """Group costs by resource type."""
        result: dict[str, float] = {}
        for e in self.estimates:
            result[e.resource_type] = result.get(e.resource_type, 0.0) + e.monthly_cost
        return result

    def top_expensive(self, n: int = 5) -> list[CostEstimate]:
        """Return the N most expensive resources."""
        return sorted(self.estimates, key=lambda e: e.monthly_cost, reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "total_monthly": round(self.total_monthly, 2),
            "total_annual": round(self.total_annual, 2),
            "resource_count": self.resource_count,
            "estimates": [
                {
                    "resource_type": e.resource_type,
                    "resource_name": e.resource_name,
                    "monthly_cost": round(e.monthly_cost, 2),
                    "notes": e.notes,
                }
                for e in self.estimates
            ],
            "by_type": {k: round(v, 2) for k, v in self.by_type().items()},
        }


# Approximate monthly pricing for common AWS/GCP/Azure resources.
# These are rough estimates for us-east-1 / default region pricing.
PRICING_TABLE: dict[str, dict[str, float]] = {
    # AWS EC2
    "aws_instance": {
        "t2.micro": 8.47,
        "t2.small": 16.94,
        "t2.medium": 33.87,
        "t3.micro": 7.59,
        "t3.small": 15.18,
        "t3.medium": 30.37,
        "t3.large": 60.74,
        "t3.xlarge": 121.47,
        "m5.large": 69.12,
        "m5.xlarge": 138.24,
        "m5.2xlarge": 276.48,
        "c5.large": 61.20,
        "c5.xlarge": 122.40,
        "r5.large": 91.98,
        "r5.xlarge": 183.96,
        "_default": 30.00,
    },
    # AWS RDS
    "aws_db_instance": {
        "db.t3.micro": 12.41,
        "db.t3.small": 24.82,
        "db.t3.medium": 49.64,
        "db.t3.large": 99.29,
        "db.r5.large": 172.80,
        "db.r5.xlarge": 345.60,
        "_default": 50.00,
    },
    # AWS S3
    "aws_s3_bucket": {
        "_default": 0.00,  # Base cost is near zero; storage is usage-based
    },
    # AWS Lambda
    "aws_lambda_function": {
        "_default": 0.00,  # Pay per invocation
    },
    # AWS DynamoDB
    "aws_dynamodb_table": {
        "_default": 25.00,
    },
    # AWS ElastiCache
    "aws_elasticache_cluster": {
        "cache.t3.micro": 11.57,
        "cache.t3.small": 23.14,
        "cache.r5.large": 159.00,
        "_default": 25.00,
    },
    # AWS ELB / ALB
    "aws_lb": {
        "_default": 16.20,
    },
    "aws_elb": {
        "_default": 16.20,
    },
    # AWS VPC / Networking
    "aws_nat_gateway": {
        "_default": 32.40,
    },
    # AWS EKS
    "aws_eks_cluster": {
        "_default": 73.00,
    },
    # AWS EBS
    "aws_ebs_volume": {
        "_default": 8.00,  # ~100GB gp3
    },
    # AWS CloudWatch
    "aws_cloudwatch_log_group": {
        "_default": 0.50,
    },
    # GCP
    "google_compute_instance": {
        "e2-micro": 6.11,
        "e2-small": 12.23,
        "e2-medium": 24.46,
        "n1-standard-1": 34.67,
        "n1-standard-2": 69.35,
        "_default": 30.00,
    },
    "google_sql_database_instance": {
        "db-f1-micro": 7.67,
        "db-g1-small": 25.51,
        "db-custom-1-3840": 48.05,
        "_default": 50.00,
    },
    "google_storage_bucket": {
        "_default": 0.00,
    },
    # Azure
    "azurerm_virtual_machine": {
        "Standard_B1s": 7.59,
        "Standard_B2s": 30.37,
        "Standard_D2s_v3": 70.08,
        "_default": 50.00,
    },
    "azurerm_sql_server": {
        "_default": 50.00,
    },
    "azurerm_storage_account": {
        "_default": 0.00,
    },
}


def _extract_instance_type(attrs: dict[str, Any]) -> str | None:
    """Try to extract an instance type from resource attributes."""
    for key in ("instance_class", "instance_type", "machine_type", "size", "sku_name"):
        if key in attrs:
            return str(attrs[key])
    return None


def estimate_resource_cost(
    resource_type: str,
    resource_name: str,
    attributes: dict[str, Any] | None = None,
) -> CostEstimate:
    """Estimate monthly cost for a single Terraform resource."""
    attributes = attributes or {}
    pricing = PRICING_TABLE.get(resource_type)

    if pricing is None:
        # Unknown resource type - cannot estimate
        return CostEstimate(
            resource_type=resource_type,
            resource_name=resource_name,
            monthly_cost=0.0,
            notes="Unknown resource type; no pricing data available.",
        )

    instance_type = _extract_instance_type(attributes)
    if instance_type and instance_type in pricing:
        cost = pricing[instance_type]
        return CostEstimate(
            resource_type=resource_type,
            resource_name=resource_name,
            monthly_cost=cost,
            notes=f"Based on instance type: {instance_type}",
        )

    cost = pricing.get("_default", 0.0)
    note = f"Default estimate for {resource_type}"
    if instance_type:
        note += f" (unrecognized instance type: {instance_type})"
    return CostEstimate(
        resource_type=resource_type,
        resource_name=resource_name,
        monthly_cost=cost,
        notes=note,
    )


def parse_terraform_plan(plan_json: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a Terraform plan JSON and extract resource changes.

    Accepts either a raw JSON string or a pre-parsed dict.
    Returns a list of dicts with keys: type, name, change_type, attributes.
    """
    if isinstance(plan_json, str):
        plan = json.loads(plan_json)
    else:
        plan = plan_json

    resources: list[dict[str, Any]] = []

    # Terraform plan format: resource_changes array
    for rc in plan.get("resource_changes", []):
        change = rc.get("change", {})
        actions = change.get("actions", [])

        if "delete" in actions and "create" not in actions:
            change_type = "delete"
        elif "create" in actions and "delete" in actions:
            change_type = "replace"
        elif "create" in actions:
            change_type = "create"
        elif "update" in actions:
            change_type = "update"
        else:
            change_type = "no-op"

        after = change.get("after") or {}
        resources.append(
            {
                "type": rc.get("type", "unknown"),
                "name": rc.get("name", "unknown"),
                "change_type": change_type,
                "attributes": after,
            }
        )

    # Also support the simpler planned_values format
    if not resources:
        _walk_modules(plan.get("planned_values", {}).get("root_module", {}), resources)

    return resources


def _walk_modules(module: dict[str, Any], resources: list[dict[str, Any]]) -> None:
    """Recursively walk planned_values modules to find resources."""
    for res in module.get("resources", []):
        resources.append(
            {
                "type": res.get("type", "unknown"),
                "name": res.get("name", "unknown"),
                "change_type": "create",
                "attributes": res.get("values", {}),
            }
        )
    for child in module.get("child_modules", []):
        _walk_modules(child, resources)


def build_cost_report(plan_json: str | dict[str, Any]) -> CostReport:
    """Build a full cost report from a Terraform plan JSON."""
    resources = parse_terraform_plan(plan_json)
    report = CostReport()

    for res in resources:
        # Only estimate costs for resources being created or updated
        if res["change_type"] in ("create", "replace", "update"):
            estimate = estimate_resource_cost(
                resource_type=res["type"],
                resource_name=res["name"],
                attributes=res.get("attributes"),
            )
            report.estimates.append(estimate)

    return report
