"""Tests for the cost_estimator module."""

from __future__ import annotations

import json
import pytest

from cost_estimator import (
    CostEstimate,
    CostReport,
    build_cost_report,
    estimate_resource_cost,
    parse_terraform_plan,
)


class TestCostEstimate:
    """Tests for the CostEstimate dataclass."""

    def test_annual_cost(self):
        est = CostEstimate(
            resource_type="aws_instance",
            resource_name="web",
            monthly_cost=100.0,
        )
        assert est.annual_cost == 1200.0

    def test_defaults(self):
        est = CostEstimate(
            resource_type="aws_instance",
            resource_name="web",
            monthly_cost=50.0,
        )
        assert est.currency == "USD"
        assert est.notes == ""

    def test_zero_cost(self):
        est = CostEstimate(
            resource_type="aws_s3_bucket",
            resource_name="logs",
            monthly_cost=0.0,
        )
        assert est.monthly_cost == 0.0
        assert est.annual_cost == 0.0


class TestCostReport:
    """Tests for the CostReport dataclass."""

    def test_empty_report(self):
        report = CostReport()
        assert report.total_monthly == 0.0
        assert report.total_annual == 0.0
        assert report.resource_count == 0

    def test_total_monthly(self):
        report = CostReport(
            estimates=[
                CostEstimate("aws_instance", "web", 100.0),
                CostEstimate("aws_rds", "db", 200.0),
            ]
        )
        assert report.total_monthly == 300.0
        assert report.total_annual == 3600.0

    def test_resource_count(self):
        report = CostReport(
            estimates=[
                CostEstimate("a", "1", 10.0),
                CostEstimate("b", "2", 20.0),
                CostEstimate("c", "3", 30.0),
            ]
        )
        assert report.resource_count == 3

    def test_by_type(self):
        report = CostReport(
            estimates=[
                CostEstimate("aws_instance", "web1", 50.0),
                CostEstimate("aws_instance", "web2", 60.0),
                CostEstimate("aws_rds", "db", 100.0),
            ]
        )
        by_type = report.by_type()
        assert by_type["aws_instance"] == 110.0
        assert by_type["aws_rds"] == 100.0

    def test_top_expensive(self):
        report = CostReport(
            estimates=[
                CostEstimate("a", "1", 10.0),
                CostEstimate("b", "2", 50.0),
                CostEstimate("c", "3", 30.0),
                CostEstimate("d", "4", 5.0),
                CostEstimate("e", "5", 40.0),
            ]
        )
        top = report.top_expensive(3)
        assert len(top) == 3
        assert top[0].monthly_cost == 50.0
        assert top[1].monthly_cost == 40.0
        assert top[2].monthly_cost == 30.0

    def test_top_expensive_more_than_available(self):
        report = CostReport(
            estimates=[
                CostEstimate("a", "1", 10.0),
            ]
        )
        top = report.top_expensive(5)
        assert len(top) == 1

    def test_to_dict(self):
        report = CostReport(
            estimates=[
                CostEstimate("aws_instance", "web", 100.0, notes="test"),
            ]
        )
        d = report.to_dict()
        assert d["total_monthly"] == 100.0
        assert d["total_annual"] == 1200.0
        assert d["resource_count"] == 1
        assert len(d["estimates"]) == 1
        assert d["estimates"][0]["resource_type"] == "aws_instance"
        assert "aws_instance" in d["by_type"]


class TestEstimateResourceCost:
    """Tests for estimate_resource_cost."""

    def test_known_instance_type(self):
        est = estimate_resource_cost(
            "aws_instance", "web", {"instance_type": "t3.micro"}
        )
        assert est.monthly_cost == 7.59
        assert "t3.micro" in est.notes

    def test_unknown_instance_type_uses_default(self):
        est = estimate_resource_cost(
            "aws_instance", "web", {"instance_type": "z99.mega"}
        )
        assert est.monthly_cost == 30.0  # _default for aws_instance
        assert "unrecognized" in est.notes

    def test_no_attributes_uses_default(self):
        est = estimate_resource_cost("aws_instance", "web")
        assert est.monthly_cost == 30.0

    def test_unknown_resource_type(self):
        est = estimate_resource_cost("aws_foo_bar", "thing")
        assert est.monthly_cost == 0.0
        assert "Unknown" in est.notes

    def test_rds_instance_class(self):
        est = estimate_resource_cost(
            "aws_db_instance", "main", {"instance_class": "db.t3.medium"}
        )
        assert est.monthly_cost == 49.64

    def test_s3_bucket_default_zero(self):
        est = estimate_resource_cost("aws_s3_bucket", "data")
        assert est.monthly_cost == 0.0

    def test_gcp_instance(self):
        est = estimate_resource_cost(
            "google_compute_instance", "vm", {"machine_type": "e2-medium"}
        )
        assert est.monthly_cost == 24.46

    def test_azure_vm(self):
        est = estimate_resource_cost(
            "azurerm_virtual_machine", "vm", {"size": "Standard_B2s"}
        )
        assert est.monthly_cost == 30.37

    def test_eks_cluster(self):
        est = estimate_resource_cost("aws_eks_cluster", "main")
        assert est.monthly_cost == 73.00

    def test_nat_gateway(self):
        est = estimate_resource_cost("aws_nat_gateway", "gw")
        assert est.monthly_cost == 32.40


class TestParseTerraformPlan:
    """Tests for parse_terraform_plan."""

    def test_resource_changes_format(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "change": {
                        "actions": ["create"],
                        "after": {"instance_type": "t3.micro"},
                    },
                },
                {
                    "type": "aws_s3_bucket",
                    "name": "data",
                    "change": {
                        "actions": ["create"],
                        "after": {},
                    },
                },
            ]
        }
        resources = parse_terraform_plan(plan)
        assert len(resources) == 2
        assert resources[0]["type"] == "aws_instance"
        assert resources[0]["change_type"] == "create"

    def test_delete_action(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "old",
                    "change": {"actions": ["delete"], "after": None},
                }
            ]
        }
        resources = parse_terraform_plan(plan)
        assert resources[0]["change_type"] == "delete"

    def test_replace_action(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "change": {
                        "actions": ["create", "delete"],
                        "after": {"instance_type": "t3.small"},
                    },
                }
            ]
        }
        resources = parse_terraform_plan(plan)
        assert resources[0]["change_type"] == "replace"

    def test_update_action(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "change": {"actions": ["update"], "after": {}},
                }
            ]
        }
        resources = parse_terraform_plan(plan)
        assert resources[0]["change_type"] == "update"

    def test_no_op_action(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "change": {"actions": ["no-op"], "after": {}},
                }
            ]
        }
        resources = parse_terraform_plan(plan)
        assert resources[0]["change_type"] == "no-op"

    def test_planned_values_format(self):
        plan = {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "type": "aws_instance",
                            "name": "web",
                            "values": {"instance_type": "t3.micro"},
                        }
                    ]
                }
            }
        }
        resources = parse_terraform_plan(plan)
        assert len(resources) == 1
        assert resources[0]["type"] == "aws_instance"

    def test_planned_values_nested_modules(self):
        plan = {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "type": "aws_instance",
                            "name": "web",
                            "values": {},
                        }
                    ],
                    "child_modules": [
                        {
                            "resources": [
                                {
                                    "type": "aws_rds_cluster",
                                    "name": "db",
                                    "values": {},
                                }
                            ]
                        }
                    ],
                }
            }
        }
        resources = parse_terraform_plan(plan)
        assert len(resources) == 2

    def test_json_string_input(self):
        plan_str = json.dumps(
            {
                "resource_changes": [
                    {
                        "type": "aws_instance",
                        "name": "web",
                        "change": {"actions": ["create"], "after": {}},
                    }
                ]
            }
        )
        resources = parse_terraform_plan(plan_str)
        assert len(resources) == 1

    def test_empty_plan(self):
        resources = parse_terraform_plan({})
        assert len(resources) == 0


class TestBuildCostReport:
    """Tests for build_cost_report (integration)."""

    def test_full_plan_report(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "change": {
                        "actions": ["create"],
                        "after": {"instance_type": "t3.large"},
                    },
                },
                {
                    "type": "aws_db_instance",
                    "name": "main",
                    "change": {
                        "actions": ["create"],
                        "after": {"instance_class": "db.t3.medium"},
                    },
                },
                {
                    "type": "aws_s3_bucket",
                    "name": "logs",
                    "change": {"actions": ["create"], "after": {}},
                },
            ]
        }
        report = build_cost_report(plan)
        assert report.resource_count == 3
        assert report.total_monthly > 0
        # t3.large + db.t3.medium + s3 default
        expected = 60.74 + 49.64 + 0.0
        assert abs(report.total_monthly - expected) < 0.01

    def test_excludes_deleted_resources(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "old",
                    "change": {"actions": ["delete"], "after": None},
                },
                {
                    "type": "aws_instance",
                    "name": "new",
                    "change": {
                        "actions": ["create"],
                        "after": {"instance_type": "t3.micro"},
                    },
                },
            ]
        }
        report = build_cost_report(plan)
        assert report.resource_count == 1
        assert report.estimates[0].resource_name == "new"

    def test_includes_updated_resources(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "change": {
                        "actions": ["update"],
                        "after": {"instance_type": "t3.small"},
                    },
                },
            ]
        }
        report = build_cost_report(plan)
        assert report.resource_count == 1

    def test_empty_plan(self):
        report = build_cost_report({})
        assert report.resource_count == 0
        assert report.total_monthly == 0.0

    def test_report_json_serializable(self):
        plan = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "change": {"actions": ["create"], "after": {}},
                }
            ]
        }
        report = build_cost_report(plan)
        d = report.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        assert len(json_str) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
