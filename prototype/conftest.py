# test_multi_tenant.py is a standalone integration script: it manages its own
# mycod subprocess and talks to it over HTTP (run it directly with
# `python test_multi_tenant.py`). Its `test_*` functions are not pytest cases —
# collecting them makes a bare `pytest` run report false ConnectionErrors
# because no daemon is up. Skip it during collection; CI runs it as a script.
collect_ignore = ["test_multi_tenant.py"]
