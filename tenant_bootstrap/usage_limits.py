"""
Usage limits enforcement for SaaS tenants.
Validates that tenants don't exceed their plan limits.
"""

import frappe
from frappe import _


# Cache key for plan limits
LIMITS_CACHE_KEY = "saas_plan_limits"


def get_plan_limits():
    """Get cached plan limits for this tenant site."""
    limits = frappe.cache().get_value(LIMITS_CACHE_KEY)

    if not limits:
        # Try to get from site config
        limits = frappe.conf.get("saas_plan_limits", {})
        if limits:
            frappe.cache().set_value(LIMITS_CACHE_KEY, limits)

    return limits or {}


def set_plan_limits(limits):
    """Store plan limits in cache and site config."""
    frappe.cache().set_value(LIMITS_CACHE_KEY, limits)

    # Also update site config for persistence
    site_config_path = frappe.get_site_path("site_config.json")
    try:
        import json
        with open(site_config_path, "r") as f:
            config = json.load(f)

        config["saas_plan_limits"] = limits

        with open(site_config_path, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        frappe.log_error(f"Failed to save plan limits to site config: {e}")


def validate_user_limit(doc, method=None):
    """Validate user creation against plan limit."""
    if doc.user_type != "System User":
        return

    # Skip for Administrator and Guest
    if doc.name in ["Administrator", "Guest"]:
        return

    limits = get_plan_limits()
    max_users = limits.get("max_users", 0)

    # 0 = Unlimited
    if not max_users:
        return

    # Count current users
    current_users = frappe.db.count("User", filters={
        "enabled": 1,
        "user_type": "System User",
        "name": ["not in", ["Administrator", "Guest", doc.name]]
    })

    if current_users >= max_users:
        frappe.throw(
            _("You have reached the maximum number of users ({0}) allowed in your plan. Please upgrade your plan to add more users.").format(max_users),
            title=_("User Limit Reached")
        )


def validate_customer_limit(doc, method=None):
    """Validate customer creation against plan limit."""
    limits = get_plan_limits()
    max_customers = limits.get("max_customers", 0)

    # 0 = Unlimited
    if not max_customers:
        return

    # Count current customers (excluding this one if it's being updated)
    filters = {}
    if not doc.is_new():
        filters["name"] = ["!=", doc.name]

    current_customers = frappe.db.count("Customer", filters=filters)

    if current_customers >= max_customers:
        frappe.throw(
            _("You have reached the maximum number of customers ({0}) allowed in your plan. Please upgrade your plan to add more customers.").format(max_customers),
            title=_("Customer Limit Reached")
        )


def validate_supplier_limit(doc, method=None):
    """Validate supplier creation against plan limit."""
    limits = get_plan_limits()
    max_suppliers = limits.get("max_suppliers", 0)

    # 0 = Unlimited
    if not max_suppliers:
        return

    # Count current suppliers (excluding this one if it's being updated)
    filters = {}
    if not doc.is_new():
        filters["name"] = ["!=", doc.name]

    current_suppliers = frappe.db.count("Supplier", filters=filters)

    if current_suppliers >= max_suppliers:
        frappe.throw(
            _("You have reached the maximum number of suppliers ({0}) allowed in your plan. Please upgrade your plan to add more suppliers.").format(max_suppliers),
            title=_("Supplier Limit Reached")
        )


def validate_company_limit(doc, method=None):
    """Validate company creation against plan limit."""
    limits = get_plan_limits()
    max_companies = limits.get("max_companies", 0)

    # 0 = Unlimited
    if not max_companies:
        return

    # Count current companies (excluding this one if it's being updated)
    filters = {}
    if not doc.is_new():
        filters["name"] = ["!=", doc.name]

    current_companies = frappe.db.count("Company", filters=filters)

    if current_companies >= max_companies:
        frappe.throw(
            _("You have reached the maximum number of companies ({0}) allowed in your plan. Please upgrade your plan to add more companies.").format(max_companies),
            title=_("Company Limit Reached")
        )


def validate_invoice_limit(doc, method=None):
    """Validate invoice creation against monthly plan limit."""
    # Only check on submit (docstatus = 1)
    if doc.docstatus != 1:
        return

    limits = get_plan_limits()
    max_invoices = limits.get("max_invoices_per_month", 0)

    # 0 = Unlimited
    if not max_invoices:
        return

    # Count invoices this month
    from frappe.utils import get_first_day, get_last_day, today
    first_day = get_first_day(today())
    last_day = get_last_day(today())

    current_invoices = frappe.db.count("Sales Invoice", filters={
        "docstatus": 1,
        "posting_date": ["between", [first_day, last_day]],
        "name": ["!=", doc.name]
    })

    if current_invoices >= max_invoices:
        frappe.throw(
            _("You have reached the maximum number of invoices ({0}) allowed per month in your plan. Please upgrade your plan to create more invoices.").format(max_invoices),
            title=_("Monthly Invoice Limit Reached")
        )


@frappe.whitelist(allow_guest=True)
def sync_plan_limits(
    max_users=0,
    max_customers=0,
    max_suppliers=0,
    max_companies=0,
    max_invoices_per_month=0,
    max_storage_gb=0
):
    """
    API to receive plan limits from the SaaS controller.
    Called when plan is assigned or changed.

    Args:
        max_users: Maximum system users (0 = unlimited)
        max_customers: Maximum customers (0 = unlimited)
        max_suppliers: Maximum suppliers (0 = unlimited)
        max_companies: Maximum companies (0 = unlimited)
        max_invoices_per_month: Maximum invoices per month (0 = unlimited)
        max_storage_gb: Maximum storage in GB

    Returns:
        dict: Success status
    """
    try:
        limits = {
            "max_users": int(max_users) if max_users else 0,
            "max_customers": int(max_customers) if max_customers else 0,
            "max_suppliers": int(max_suppliers) if max_suppliers else 0,
            "max_companies": int(max_companies) if max_companies else 0,
            "max_invoices_per_month": int(max_invoices_per_month) if max_invoices_per_month else 0,
            "max_storage_gb": float(max_storage_gb) if max_storage_gb else 0
        }

        set_plan_limits(limits)

        return {"success": True, "message": "Plan limits updated", "limits": limits}

    except Exception as e:
        frappe.log_error(f"Failed to sync plan limits: {e}")
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def get_current_limits():
    """
    API to get current plan limits.

    Returns:
        dict: Current plan limits
    """
    return {
        "success": True,
        "limits": get_plan_limits()
    }
