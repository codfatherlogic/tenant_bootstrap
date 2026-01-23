"""
Tenant Site Setup Functions

These functions are designed to be called via `bench execute` on tenant sites
to set up the company, user, and complete the setup wizard.

This app must be installed on ALL tenant sites to enable automated provisioning.

Usage:
    bench --site tenant.example.com execute \
        tenant_bootstrap.setup.setup_company \
        --kwargs '{"config_b64": "..."}'

    bench --site tenant.example.com execute \
        tenant_bootstrap.setup.create_user \
        --kwargs '{"config_b64": "..."}'
"""

import base64
import json
import traceback

import frappe


def setup_company(config_b64):
    """
    Set up company on a tenant site.

    Called via bench execute with base64-encoded configuration.

    Args:
        config_b64: Base64-encoded JSON containing:
            - company_name
            - company_abbr
            - country
            - currency
            - chart_of_accounts
            - fy_name
            - fy_start_date
            - fy_end_date

    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        # Decode configuration
        config = json.loads(base64.b64decode(config_b64).decode())

        company_name = config["company_name"]
        company_abbr = config["company_abbr"]
        country = config["country"]
        currency = config["currency"]
        chart_of_accounts = config.get("chart_of_accounts", "Standard")
        fy_name = config["fy_name"]
        fy_start_date = config["fy_start_date"]
        fy_end_date = config["fy_end_date"]

        print(f"[SETUP] Company: {company_name}, Abbr: {company_abbr}, Country: {country}")

        # Set ignore permissions for all operations
        frappe.flags.ignore_permissions = True

        # Step 1: Mark setup complete in site_config.json
        site_config_path = frappe.get_site_path("site_config.json")
        with open(site_config_path) as f:
            site_config = json.load(f)
        site_config["setup_complete"] = 1
        with open(site_config_path, "w") as f:
            json.dump(site_config, f, indent=1)
        print("[SETUP] site_config.json updated with setup_complete=1")

        # Step 2: Mark setup complete in System Settings and disable onboarding
        frappe.db.set_single_value("System Settings", "setup_complete", 1)
        frappe.db.set_single_value("System Settings", "enable_onboarding", 0)
        frappe.db.set_single_value("System Settings", "country", country)
        frappe.db.set_single_value("System Settings", "language", "en")
        frappe.db.set_single_value("System Settings", "time_zone", "Asia/Kolkata")
        frappe.db.commit()
        print("[SETUP] System Settings updated with setup_complete=1, enable_onboarding=0")

        # Step 2b: Mark all installed apps as setup complete in Installed Application table
        # This is CRITICAL for ERPNext v16 - frappe.is_setup_complete() checks this table
        for app_name in ["frappe", "erpnext"]:
            if frappe.db.exists("Installed Application", {"app_name": app_name}):
                frappe.db.set_value(
                    "Installed Application",
                    {"app_name": app_name},
                    "is_setup_complete",
                    1
                )
                print(f"[SETUP] Marked {app_name} as setup complete in Installed Application")
        frappe.db.commit()

        # Step 2c: Set desktop home page to prevent setup wizard from being the default landing page
        # ROOT CAUSE FIX: Without this, desktop:home_page defaults to "setup-wizard" causing infinite redirect
        frappe.db.set_default("desktop:home_page", "home")
        frappe.db.commit()
        print("[SETUP] Set desktop:home_page to 'home' (prevents setup wizard redirect)")

        # Step 3: Create Warehouse Types (required for ERPNext Stock module)
        for wt in ["Transit", "Stores", "Goods In Transit", "Virtual"]:
            if not frappe.db.exists("Warehouse Type", wt):
                doc = frappe.get_doc({"doctype": "Warehouse Type", "name": wt})
                doc.insert(ignore_permissions=True)
                print(f"[SETUP] Created Warehouse Type: {wt}")
        frappe.db.commit()

        # Step 4: Create Company with Chart of Accounts
        frappe.flags.in_setup_wizard = True
        if not frappe.db.exists("Company", company_name):
            print(f"[SETUP] Creating company: {company_name}")
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": company_name,
                "abbr": company_abbr,
                "country": country,
                "default_currency": currency,
                "enable_perpetual_inventory": 1,
                "chart_of_accounts": chart_of_accounts
            })
            company.insert(ignore_permissions=True)

            # Set company as default
            frappe.db.set_default("company", company_name)
            frappe.db.set_default("country", country)
            frappe.db.set_default("currency", currency)
            frappe.db.commit()
            print(f"[SETUP] Company created: {company_name}")
        else:
            # Company exists, ensure defaults are set
            frappe.db.set_default("company", company_name)
            frappe.db.set_default("country", country)
            frappe.db.set_default("currency", currency)
            frappe.db.commit()
            print(f"[SETUP] Company already exists: {company_name}")
        frappe.flags.in_setup_wizard = False

        # Step 5: Create Fiscal Year
        if not frappe.db.exists("Fiscal Year", fy_name):
            print(f"[SETUP] Creating fiscal year: {fy_name}")
            fy = frappe.get_doc({
                "doctype": "Fiscal Year",
                "year": fy_name,
                "year_start_date": fy_start_date,
                "year_end_date": fy_end_date,
                "is_short_year": 0
            })
            fy.insert(ignore_permissions=True)
            frappe.db.set_default("fiscal_year", fy_name)
            frappe.db.commit()
            print(f"[SETUP] Fiscal Year created: {fy_name}")
        else:
            frappe.db.set_default("fiscal_year", fy_name)
            frappe.db.commit()
            print(f"[SETUP] Fiscal Year exists: {fy_name}")

        # Step 6: Configure ERPNext Settings (important for skipping setup wizard)
        if frappe.db.exists("DocType", "ERPNext Settings"):
            try:
                erpnext_settings = frappe.get_single("ERPNext Settings")
                erpnext_settings.setup_complete = 1
                erpnext_settings.save(ignore_permissions=True)
                frappe.db.commit()
                print("[SETUP] ERPNext Settings updated with setup_complete=1")
            except Exception as e:
                print(f"[SETUP] Warning: Could not update ERPNext Settings: {e}")

        # Step 7: Set Global Defaults
        if frappe.db.exists("DocType", "Global Defaults"):
            try:
                global_defaults = frappe.get_single("Global Defaults")
                global_defaults.default_company = company_name
                global_defaults.current_fiscal_year = fy_name
                global_defaults.country = country
                global_defaults.default_currency = currency
                global_defaults.save(ignore_permissions=True)
                frappe.db.commit()
                print("[SETUP] Global Defaults updated")
            except Exception as e:
                print(f"[SETUP] Warning: Could not update Global Defaults: {e}")

        # Step 8: Set Stock Settings defaults
        if frappe.db.exists("DocType", "Stock Settings"):
            try:
                stock_settings = frappe.get_single("Stock Settings")
                stock_settings.stock_uom = "Nos"
                stock_settings.save(ignore_permissions=True)
                frappe.db.commit()
                print("[SETUP] Stock Settings updated")
            except Exception as e:
                print(f"[SETUP] Warning: Could not update Stock Settings: {e}")

        # Step 9: Clear all caches to apply changes
        frappe.clear_cache()
        print("[SETUP] Cache cleared")

        # Verify company was created
        if frappe.db.exists("Company", company_name):
            print("SETUP_SUCCESS")
            return {"success": True, "message": f"Company {company_name} created successfully"}
        else:
            print(f"SETUP_FAILED: Company '{company_name}' not found after creation")
            return {"success": False, "message": f"Company '{company_name}' not found after creation"}

    except Exception as e:
        print(f"SETUP_FAILED: {e!s}")
        traceback.print_exc()
        return {"success": False, "message": str(e)}


def create_user(config_b64):
    """
    Create a user on a tenant site.

    Called via bench execute with base64-encoded configuration.

    Args:
        config_b64: Base64-encoded JSON containing:
            - email
            - first_name
            - last_name
            - password

    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        from frappe.utils.password import update_password

        # Decode configuration
        config = json.loads(base64.b64decode(config_b64).decode())

        email = config["email"]
        first_name = config.get("first_name", "User")
        last_name = config.get("last_name", "")
        password = config["password"]

        print(f"[USER] Creating/updating user: {email}")

        # Set ignore permissions
        frappe.flags.ignore_permissions = True

        if frappe.db.exists("User", email):
            # Update existing user password
            update_password(email, password)
            frappe.db.commit()
            # Ensure user is enabled and has correct roles
            user = frappe.get_doc("User", email)
            user.enabled = 1
            if "System Manager" not in [r.role for r in user.roles]:
                user.add_roles("System Manager")
            user.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"USER_SUCCESS: User {email} exists, password and roles updated")
            return {"success": True, "message": f"User {email} updated"}
        else:
            # Create new user
            user = frappe.get_doc({
                "doctype": "User",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "enabled": 1,
                "user_type": "System User",
                "send_welcome_email": 0,
            })
            user.insert(ignore_permissions=True)

            # Set password after creation
            update_password(email, password)
            frappe.db.commit()

            # Add System Manager role
            user.add_roles("System Manager")
            frappe.db.commit()
            print(f"USER_SUCCESS: User {email} created successfully")

        # Also set Administrator password for "Login as Admin" functionality
        try:
            update_password("Administrator", password)
            frappe.db.commit()
            print("[USER] Administrator password also updated")
        except Exception as admin_err:
            print(f"[USER] Warning: Could not update Administrator password: {admin_err}")

        return {"success": True, "message": f"User {email} created/updated"}

    except Exception as e:
        print(f"USER_FAILED: {e!s}")
        traceback.print_exc()
        return {"success": False, "message": str(e)}
