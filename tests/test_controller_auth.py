"""require_controller lets only a caller with the site's secret through (runs without a bench)."""

import sys
import types
import unittest


class _PermissionError(Exception):
	pass


def _fake_frappe(secret, header, has_request=True):
	fake = types.ModuleType("frappe")
	fake.PermissionError = _PermissionError
	fake.conf = {"tenant_bootstrap_secret": secret} if secret is not None else {}
	fake.request = object() if has_request else None
	fake.get_request_header = lambda name: header if name == "X-Tenant-Bootstrap-Secret" else None

	def throw(msg, exc=Exception):
		raise exc(msg)

	fake.throw = throw
	return fake


def _check(secret, header, has_request=True):
	sys.modules["frappe"] = _fake_frappe(secret, header, has_request)
	sys.modules.pop("tenant_bootstrap.controller_auth", None)
	from tenant_bootstrap.controller_auth import require_controller

	require_controller()


class TestRequireController(unittest.TestCase):
	def tearDown(self):
		sys.modules.pop("frappe", None)
		sys.modules.pop("tenant_bootstrap.controller_auth", None)

	def test_right_secret_passes(self):
		_check("s3cret-value", "s3cret-value")

	def test_wrong_secret_refused(self):
		with self.assertRaises(_PermissionError):
			_check("s3cret-value", "guess")

	def test_missing_header_refused(self):
		with self.assertRaises(_PermissionError):
			_check("s3cret-value", None)

	def test_site_without_secret_refuses_everyone(self):
		with self.assertRaises(_PermissionError):
			_check(None, "")
		with self.assertRaises(_PermissionError):
			_check("", "")

	def test_no_request_refused(self):
		with self.assertRaises(_PermissionError):
			_check("s3cret-value", "s3cret-value", has_request=False)


if __name__ == "__main__":
	unittest.main()
