"""
Only the SaaS controller may call this app's controller endpoints.

They have to be reachable without a user login (the controller calls them from outside the site), so
`allow_guest=True` stays, but every call must carry the shared secret from the site's config:

    bench --site tenant.example.com set-config tenant_bootstrap_secret "<long random value>"

and the controller sends it in the `X-Tenant-Bootstrap-Secret` header. A site with no secret set
refuses every call (fail closed): before this, anyone on the internet could rewrite a tenant's plan
limits or read its usage.
"""

import hmac

import frappe

SECRET_KEY = "tenant_bootstrap_secret"
SECRET_HEADER = "X-Tenant-Bootstrap-Secret"


def require_controller():
	"""Raise PermissionError unless the request carries this site's controller secret."""
	expected = frappe.conf.get(SECRET_KEY) or ""
	sent = (frappe.get_request_header(SECRET_HEADER) or "") if frappe.request else ""
	if not expected or not sent or not hmac.compare_digest(str(expected), str(sent)):
		frappe.throw("Not permitted", frappe.PermissionError)
